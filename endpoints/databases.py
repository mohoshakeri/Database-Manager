from datetime import date, datetime, time
from math import ceil
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from core.config import DatabaseKind, settings
from dependencies.auth import require_csrf, require_user
from schemas.database import ColumnSchema, DatabaseConnectionSchema, TableSchema
from services.database import ALLOWED_COLUMN_TYPES, database_service

router: APIRouter = APIRouter(tags=["Databases"])
templates: Jinja2Templates = Jinja2Templates(directory="templates")




def _input_value(value: Any, column_type: str) -> str:
    if value is None:
        return ""
    lowered_type: str = column_type.lower()

    if isinstance(value, datetime):
        if "timestamp" in lowered_type or "datetime" in lowered_type:
            return value.replace(tzinfo=None).isoformat(timespec="seconds")
        if "date" in lowered_type:
            return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.replace(tzinfo=None).isoformat(timespec="seconds")

    text_value: str = str(value).strip()
    if "timestamp" in lowered_type or "datetime" in lowered_type:
        normalized: str = text_value.replace(" ", "T")
        if "+" in normalized:
            normalized = normalized.split("+", 1)[0]
        if normalized.endswith("Z"):
            normalized = normalized[:-1]
        if "." in normalized:
            head, tail = normalized.split(".", 1)
            normalized = head + "." + tail[:6]
        return normalized
    if "date" in lowered_type and "time" not in lowered_type:
        return text_value[:10]
    return text_value

def _redirect_if_needed(user: str | RedirectResponse) -> RedirectResponse | None:
    if isinstance(user, RedirectResponse):
        return user
    return None


def _error_message(error: Exception) -> str:
    detail: str = str(error).strip()
    if isinstance(error, SQLAlchemyError):
        return f"خطای دیتابیس: {detail or error.__class__.__name__}"
    return detail or error.__class__.__name__


def _operation_error(label: str, error: Exception) -> str:
    return f"{label}: {_error_message(error)}"


def _url_with_error(url: str, error: str) -> str:
    separator: str = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'error': error})}"


def _table_url(connection_id: str, table_name: str, page: int = 1, page_size: int = 25, error: str = "") -> str:
    safe_page: int = max(page, 1)
    safe_page_size: int = min(max(page_size, 10), 100)
    url: str = f"/db/{connection_id}/tables/{table_name}?page={safe_page}&page_size={safe_page_size}"
    if error:
        return _url_with_error(url, error)
    return url


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: str | RedirectResponse = Depends(require_user)) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    connections: list[DatabaseConnectionSchema] = database_service.list_connections()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "settings": settings, "connections": connections, "error": "", "message": ""},
    )


@router.post("/databases/create")
def create_database(
    kind: DatabaseKind = Form(...),
    database_name: str = Form(...),
    user: str | RedirectResponse = Depends(require_user),
    _csrf: None = Depends(require_csrf),
) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    try:
        database_service.create_database(kind=kind, database_name=database_name)
    except Exception as error:
        return RedirectResponse(url=_url_with_error("/", _operation_error("ساخت دیتابیس ناموفق بود", error)), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/databases/drop")
def drop_database(
    kind: DatabaseKind = Form(...),
    database_name: str = Form(...),
    user: str | RedirectResponse = Depends(require_user),
    _csrf: None = Depends(require_csrf),
) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    try:
        database_service.drop_database(kind=kind, database_name=database_name)
    except Exception as error:
        return RedirectResponse(url=_url_with_error("/", _operation_error("حذف دیتابیس ناموفق بود", error)), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/db/{connection_id}", response_class=HTMLResponse)
def database_detail(request: Request, connection_id: str, user: str | RedirectResponse = Depends(require_user)) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    try:
        connection: DatabaseConnectionSchema = database_service.get_connection(connection_id)
        tables: list[TableSchema] = database_service.list_tables(connection_id)
    except Exception as error:
        return templates.TemplateResponse("error.html", {"request": request, "settings": settings, "error": _error_message(error)}, status_code=400)
    return templates.TemplateResponse(
        "database.html",
        {
            "request": request,
            "settings": settings,
            "connection": connection,
            "tables": tables,
            "column_types": ALLOWED_COLUMN_TYPES.keys(),
            "error": "",
        },
    )


@router.post("/db/{connection_id}/tables")
def create_table(
    connection_id: str,
    table_name: str = Form(...),
    columns_spec: str = Form(...),
    user: str | RedirectResponse = Depends(require_user),
    _csrf: None = Depends(require_csrf),
) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    try:
        database_service.create_table(connection_id=connection_id, table_name=table_name, columns_spec=columns_spec)
    except Exception as error:
        return RedirectResponse(url=_url_with_error(f"/db/{connection_id}", _operation_error("ساخت جدول ناموفق بود", error)), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/db/{connection_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/db/{connection_id}/tables/{table_name}/drop")
def drop_table(
    connection_id: str,
    table_name: str,
    user: str | RedirectResponse = Depends(require_user),
    _csrf: None = Depends(require_csrf),
) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    try:
        database_service.drop_table(connection_id=connection_id, table_name=table_name)
    except Exception as error:
        return RedirectResponse(url=_url_with_error(f"/db/{connection_id}", _operation_error("حذف جدول ناموفق بود", error)), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/db/{connection_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/db/{connection_id}/tables/{table_name}", response_class=HTMLResponse)
def table_detail(
    request: Request,
    connection_id: str,
    table_name: str,
    page: int = 1,
    page_size: int = 25, 
    user: str | RedirectResponse = Depends(require_user),
) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    try:
        connection: DatabaseConnectionSchema = database_service.get_connection(connection_id)
        columns: list[ColumnSchema] = database_service.list_columns(connection_id, table_name)
        search: str = str(request.query_params.get("search", "")).strip()
        sort_by: str = str(request.query_params.get("sort_by", "")).strip()
        sort_dir: str = str(request.query_params.get("sort_dir", "asc")).strip().lower()
        if sort_dir not in {"asc", "desc"}:
            sort_dir = "asc"
        filters: dict[str, str] = {
            key.removeprefix("filter__"): value
            for key, value in request.query_params.items()
            if key.startswith("filter__") and str(value).strip()
        }
        total_rows: int = database_service.count_rows(connection_id, table_name, search=search, filters=filters)
        safe_page_size: int = min(max(page_size, 10), 100)
        total_pages: int = max(ceil(total_rows / safe_page_size), 1)
        safe_page: int = min(max(page, 1), total_pages)
        rows: list[dict[str, Any]] = database_service.fetch_rows(
            connection_id,
            table_name,
            page=safe_page,
            page_size=safe_page_size,
            search=search,
            filters=filters,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        primary_columns: list[ColumnSchema] = [column for column in columns if column.primary_key]
        primary_key: str = primary_columns[0].name if len(primary_columns) == 1 else ""
        filter_query_pairs: list[tuple[str, str | int]] = [("page_size", safe_page_size)]
        if search:
            filter_query_pairs.append(("search", search))
        filter_query_pairs.extend((f"filter__{key}", value) for key, value in filters.items() if value)
        query_pairs: list[tuple[str, str | int]] = [*filter_query_pairs]
        if sort_by:
            query_pairs.extend([("sort_by", sort_by), ("sort_dir", sort_dir)])
        filter_query_suffix: str = "&" + urlencode(filter_query_pairs) if filter_query_pairs else ""
        query_suffix: str = "&" + urlencode(query_pairs) if query_pairs else ""
    except Exception as error:
        return templates.TemplateResponse("error.html", {"request": request, "settings": settings, "error": _error_message(error)}, status_code=400)
    return templates.TemplateResponse(
        "table.html",
        {
            "request": request,
            "settings": settings,
            "connection": connection,
            "table_name": table_name,
            "columns": columns,
            "rows": rows,
            "primary_key": primary_key,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_rows": total_rows,
            "total_pages": total_pages,
            "has_previous": safe_page > 1,
            "has_next": safe_page < total_pages,
            "column_types": ALLOWED_COLUMN_TYPES.keys(),
            "search": search,
            "filters": filters,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "query_suffix": query_suffix,
            "filter_query_suffix": filter_query_suffix,
            "input_value": _input_value,
            "error": "",
        },
    )


@router.post("/db/{connection_id}/tables/{table_name}/columns")
def add_column(
    connection_id: str,
    table_name: str,
    column_name: str = Form(...),
    column_type: str = Form(...),
    nullable: bool = Form(False),
    page: int = Form(1),
    page_size: int = Form(25),
    user: str | RedirectResponse = Depends(require_user),
    _csrf: None = Depends(require_csrf),
) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    try:
        database_service.add_column(connection_id, table_name, column_name, column_type, nullable)
    except Exception as error:
        return RedirectResponse(url=_table_url(connection_id, table_name, page, page_size, _operation_error("افزودن ستون ناموفق بود", error)), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=_table_url(connection_id, table_name, page, page_size), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/db/{connection_id}/tables/{table_name}/columns/{column_name}/drop")
def drop_column(
    connection_id: str,
    table_name: str,
    column_name: str,
    page: int = Form(1),
    page_size: int = Form(25),
    user: str | RedirectResponse = Depends(require_user),
    _csrf: None = Depends(require_csrf),
) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    try:
        database_service.drop_column(connection_id, table_name, column_name)
    except Exception as error:
        return RedirectResponse(url=_table_url(connection_id, table_name, page, page_size, _operation_error("حذف ستون ناموفق بود", error)), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=_table_url(connection_id, table_name, page, page_size), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/db/{connection_id}/tables/{table_name}/rows")
async def insert_row(request: Request, connection_id: str, table_name: str, user: str | RedirectResponse = Depends(require_user), _csrf: None = Depends(require_csrf)) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    form = await request.form()
    page: int = int(str(form.get("_page", "1")))
    page_size: int = int(str(form.get("_page_size", "25")))
    payload: dict[str, Any] = {key: value for key, value in form.items() if not key.startswith("_") and key != "csrf_token"}
    try:
        database_service.insert_row(connection_id=connection_id, table_name=table_name, payload=payload)
    except Exception as error:
        return RedirectResponse(url=_table_url(connection_id, table_name, page, page_size, _operation_error("افزودن ردیف ناموفق بود", error)), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=_table_url(connection_id, table_name, page, page_size), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/db/{connection_id}/tables/{table_name}/rows/update")
async def update_row(request: Request, connection_id: str, table_name: str, user: str | RedirectResponse = Depends(require_user), _csrf: None = Depends(require_csrf)) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    form = await request.form()
    primary_key: str = str(form.get("_primary_key", ""))
    primary_value: str = str(form.get("_primary_value", ""))
    page: int = int(str(form.get("_page", "1")))
    page_size: int = int(str(form.get("_page_size", "25")))
    payload: dict[str, Any] = {key: value for key, value in form.items() if not key.startswith("_") and key != "csrf_token"}
    try:
        database_service.update_row(connection_id, table_name, primary_key, primary_value, payload)
    except Exception as error:
        return RedirectResponse(url=_table_url(connection_id, table_name, page, page_size, _operation_error("ذخیره ردیف ناموفق بود", error)), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=_table_url(connection_id, table_name, page, page_size), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/db/{connection_id}/tables/{table_name}/rows/bulk")
async def bulk_rows(request: Request, connection_id: str, table_name: str, user: str | RedirectResponse = Depends(require_user), _csrf: None = Depends(require_csrf)) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    form = await request.form()
    primary_key: str = str(form.get("_primary_key", ""))
    page: int = int(str(form.get("_page", "1")))
    page_size: int = int(str(form.get("_page_size", "25")))
    action: str = str(form.get("_bulk_action", "save_changes"))
    selected_rows: set[str] = {str(value) for value in form.getlist("_selected_rows")}
    dirty_rows: set[str] = {str(value) for value in form.getlist("_dirty_rows")}

    try:
        if action == "delete_selected":
            if not selected_rows:
                raise ValueError("No rows selected")
            for row_index in selected_rows:
                primary_value: str = str(form.get(f"_row_{row_index}_primary_value", ""))
                database_service.delete_row(connection_id, table_name, primary_key, primary_value)
        else:
            if not dirty_rows:
                raise ValueError("No changed rows")
            for row_index in dirty_rows:
                primary_value = str(form.get(f"_row_{row_index}_primary_value", ""))
                prefix: str = f"row_{row_index}__"
                payload: dict[str, Any] = {
                    key[len(prefix):]: value
                    for key, value in form.items()
                    if key.startswith(prefix)
                }
                database_service.update_row(connection_id, table_name, primary_key, primary_value, payload)
    except Exception as error:
        label: str = "حذف گروهی ردیف‌ها ناموفق بود" if action == "delete_selected" else "ذخیره گروهی تغییرات ناموفق بود"
        return RedirectResponse(url=_table_url(connection_id, table_name, page, page_size, _operation_error(label, error)), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=_table_url(connection_id, table_name, page, page_size), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/db/{connection_id}/tables/{table_name}/rows/delete")
def delete_row(
    connection_id: str,
    table_name: str,
    primary_key: str = Form(...),
    primary_value: str = Form(...),
    page: int = Form(1),
    page_size: int = Form(25),
    user: str | RedirectResponse = Depends(require_user),
    _csrf: None = Depends(require_csrf),
) -> Response:
    redirect: RedirectResponse | None = _redirect_if_needed(user)
    if redirect:
        return redirect
    try:
        database_service.delete_row(connection_id, table_name, primary_key, primary_value)
    except Exception as error:
        return RedirectResponse(url=_table_url(connection_id, table_name, page, page_size, _operation_error("حذف ردیف ناموفق بود", error)), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=_table_url(connection_id, table_name, page, page_size), status_code=status.HTTP_303_SEE_OTHER)
