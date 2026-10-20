import csv
import io
from uuid import UUID

from redis.asyncio import Redis
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.link import BulkImportError, BulkImportResponse, CreateLinkRequest
from app.services.domain_blocklist import BlockedDestinationError
from app.services.links import (
    AliasGenerationError,
    CampaignNotFoundError,
    DuplicateAliasError,
    LinkCacheUnavailableError,
    create_link,
)


class InvalidCsvError(ValueError):
    """Raised when a CSV cannot be parsed as an import document."""


_HEADER_ALIASES = {
    "alias": "custom_alias",
    "short_code": "custom_alias",
    "url": "destination_url",
}


def _normalise_headers(headers: list[str]) -> list[str]:
    if not headers:
        raise InvalidCsvError("CSV must include a header row")

    normalised: list[str] = []
    for header in headers:
        cleaned = header.strip().lower()
        canonical = _HEADER_ALIASES.get(cleaned, cleaned)
        if not canonical:
            raise InvalidCsvError("CSV contains an empty column name")
        if canonical in normalised:
            raise InvalidCsvError(f"CSV contains duplicate column '{canonical}'")
        normalised.append(canonical)

    if "destination_url" not in normalised:
        raise InvalidCsvError("CSV must include a 'destination_url' column")
    return normalised


def _optional_value(row: dict[str, str], column: str) -> str | None:
    value = row.get(column, "")
    if column == "password":
        return value or None
    value = value.strip()
    return value or None


def _request_from_row(row: dict[str, str]) -> CreateLinkRequest:
    payload: dict[str, object] = {
        "destination_url": row.get("destination_url", "").strip(),
        "rules": {},
    }

    custom_alias = _optional_value(row, "custom_alias")
    if custom_alias is not None:
        payload["custom_alias"] = custom_alias

    campaign_id = _optional_value(row, "campaign_id")
    if campaign_id is not None:
        payload["campaign_id"] = campaign_id

    rules: dict[str, str] = {}
    for column in ("password", "expires_at", "click_limit"):
        value = _optional_value(row, column)
        if value is not None:
            rules[column] = value
    payload["rules"] = rules
    return CreateLinkRequest.model_validate(payload)


def _validation_error_message(error: ValidationError) -> str:
    first_error = error.errors()[0]
    location = ".".join(str(part) for part in first_error["loc"])
    message = str(first_error["msg"])
    if location == "destination_url":
        return f"Destination URL is invalid: {message}"
    if location:
        return f"{location}: {message}"
    return message


def _row_error(row_number: int, message: str) -> BulkImportError:
    return BulkImportError(row=row_number, error=message)


async def import_links_from_csv(
    *,
    content: bytes,
    user_id: UUID,
    db: AsyncSession,
    redis: Redis,
) -> BulkImportResponse:
    try:
        csv_text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InvalidCsvError("CSV must be UTF-8 encoded") from error

    reader = csv.reader(io.StringIO(csv_text), strict=True)
    try:
        headers = _normalise_headers(next(reader))
    except StopIteration as error:
        raise InvalidCsvError("CSV must include a header row") from error
    except csv.Error as error:
        raise InvalidCsvError(f"Malformed CSV header: {error}") from error

    total_processed = 0
    successful_imports = 0
    errors: list[BulkImportError] = []
    imported_aliases: set[str] = set()

    while True:
        try:
            values = next(reader)
        except StopIteration:
            break
        except csv.Error as error:
            row_number = max(reader.line_num, total_processed + 2)
            total_processed += 1
            errors.append(_row_error(row_number, f"Malformed CSV row: {error}"))
            break

        row_number = reader.line_num
        total_processed += 1

        if not values or all(not value.strip() for value in values):
            errors.append(_row_error(row_number, "Row is blank"))
            continue
        if len(values) > len(headers):
            errors.append(_row_error(row_number, "Row has more fields than the header"))
            continue

        row = {
            header: values[index] if index < len(values) else ""
            for index, header in enumerate(headers)
        }
        try:
            payload = _request_from_row(row)
        except ValidationError as error:
            errors.append(_row_error(row_number, _validation_error_message(error)))
            continue

        alias = payload.custom_alias
        if alias is not None and alias in imported_aliases:
            errors.append(_row_error(row_number, f"Alias '{alias}' is duplicated in this file"))
            continue

        try:
            await create_link(
                payload=payload,
                user_id=user_id,
                db=db,
                redis=redis,
            )
        except DuplicateAliasError:
            alias_label = alias or "generated alias"
            errors.append(_row_error(row_number, f"Alias '{alias_label}' is already taken"))
            continue
        except BlockedDestinationError as error:
            errors.append(_row_error(row_number, str(error)))
            continue
        except CampaignNotFoundError:
            errors.append(_row_error(row_number, "Campaign not found or not owned by current user"))
            continue
        except LinkCacheUnavailableError:
            errors.append(_row_error(row_number, "Routing cache unavailable"))
            continue
        except AliasGenerationError:
            errors.append(_row_error(row_number, "Could not allocate a unique alias"))
            continue

        successful_imports += 1
        if alias is not None:
            imported_aliases.add(alias)

    return BulkImportResponse(
        total_processed=total_processed,
        successful_imports=successful_imports,
        failed_imports=len(errors),
        errors=errors,
    )
