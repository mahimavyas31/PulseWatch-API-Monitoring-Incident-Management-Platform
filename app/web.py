"""Server-rendered dashboard (Jinja2 + Bootstrap)."""
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import CheckResult, Incident, Monitor, User
from app.schemas import MonitorCreate, UserCreate
from app.security import COOKIE_NAME, create_token, web_user
from app.services import stats
from app.services.checking import run_check
from app.services.incident_manager import record_result
from app.services.url_validator import UnsafeURLError, validate_destination
from app.services.users import EmailTaken, authenticate, create_user
from app.utils import as_utc

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["dt"] = lambda v: "" if v is None else as_utc(v).strftime("%Y-%m-%d %H:%M:%S UTC")

router = APIRouter(include_in_schema=False)


def render(request: Request, name: str, user: User | None = None, status_code: int = 200, **ctx):
    return templates.TemplateResponse(request, name, {"user": user, **ctx}, status_code=status_code)


def login_redirect(user: User) -> RedirectResponse:
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie(COOKIE_NAME, create_token(user.id), httponly=True, samesite="lax",
                    secure=settings.cookie_secure, max_age=settings.token_expire_minutes * 60)
    return resp


@router.get("/")
def index(user: User | None = Depends(web_user)):
    return RedirectResponse("/dashboard" if user else "/login", status_code=303)


@router.get("/login")
def login_page(request: Request, user: User | None = Depends(web_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "login.html")


@router.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...),
                 db: Session = Depends(get_db)):
    user = authenticate(db, email, password)
    if user is None:
        return render(request, "login.html", status_code=401, error="Invalid email or password",
                      email=email)
    return login_redirect(user)


@router.get("/register")
def register_page(request: Request):
    return render(request, "register.html")


@router.post("/register")
def register_submit(request: Request, email: str = Form(...), password: str = Form(...),
                    db: Session = Depends(get_db)):
    try:
        data = UserCreate(email=email, password=password)
    except ValidationError as exc:
        msg = exc.errors()[0]["msg"].removeprefix("Value error, ")
        return render(request, "register.html", status_code=422, error=msg, email=email)
    try:
        user = create_user(db, data.email, data.password)
    except EmailTaken:
        return render(request, "register.html", status_code=409,
                      error="Email already registered", email=email)
    return login_redirect(user)


@router.post("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


def _dashboard(request, db, user, error=None, status_code=200):
    monitors = db.scalars(select(Monitor).where(Monitor.user_id == user.id)
                          .order_by(Monitor.id)).all()
    rows = []
    for m in monitors:
        last = stats.latest_check(db, m.id)
        rows.append({"m": m, "status": stats.current_status(db, m),
                     "slow": bool(last and last.is_anomaly),
                     "uptime": stats.uptime_percent(db, m.id),
                     "last_ms": last.response_ms if last else None})
    open_incidents = db.scalars(
        select(Incident).join(Monitor, Monitor.id == Incident.monitor_id)
        .where(Monitor.user_id == user.id, Incident.status == "open")).all()
    return render(request, "dashboard.html", user, status_code, rows=rows,
                  open_incidents=open_incidents, error=error)


@router.get("/dashboard")
def dashboard(request: Request, user: User | None = Depends(web_user),
              db: Session = Depends(get_db)):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return _dashboard(request, db, user)


@router.post("/dashboard/monitors")
def add_monitor(request: Request, name: str = Form(...), url: str = Form(...),
                interval_seconds: int = Form(60), timeout_seconds: int = Form(10),
                expected_status: str = Form("200-399"), expected_body: str = Form(""),
                webhook_url: str = Form(""), is_public: bool = Form(False),
                user: User | None = Depends(web_user), db: Session = Depends(get_db)):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        data = MonitorCreate(name=name, url=url, interval_seconds=interval_seconds,
                             timeout_seconds=timeout_seconds, expected_status=expected_status,
                             expected_body=expected_body, webhook_url=webhook_url,
                             is_public=is_public)
        validate_destination(data.url)
        if data.webhook_url:
            validate_destination(data.webhook_url)
    except ValidationError as exc:
        err = exc.errors()[0]
        msg = f"{err['loc'][-1]}: {err['msg'].removeprefix('Value error, ')}"
        return _dashboard(request, db, user, error=msg, status_code=422)
    except UnsafeURLError as exc:
        return _dashboard(request, db, user, error=str(exc), status_code=422)
    db.add(Monitor(user_id=user.id, **data.model_dump()))
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)


def _owned(db: Session, user: User, monitor_id: int) -> Monitor | None:
    m = db.get(Monitor, monitor_id)
    return m if m and m.user_id == user.id else None


@router.get("/dashboard/monitors/{monitor_id}")
def monitor_detail(monitor_id: int, request: Request, user: User | None = Depends(web_user),
                   db: Session = Depends(get_db)):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    m = _owned(db, user, monitor_id)
    if m is None:
        return RedirectResponse("/dashboard", status_code=303)
    checks = db.scalars(select(CheckResult).where(CheckResult.monitor_id == m.id)
                        .order_by(CheckResult.id.desc()).limit(100)).all()
    incidents = db.scalars(select(Incident).where(Incident.monitor_id == m.id)
                           .order_by(Incident.id.desc()).limit(20)).all()
    series = list(reversed(checks))
    return render(request, "monitor_detail.html", user, m=m,
                  status=stats.current_status(db, m),
                  uptime_24h=stats.uptime_percent(db, m.id, 24),
                  uptime_7d=stats.uptime_percent(db, m.id, 24 * 7),
                  avg_ms=stats.avg_response_ms(db, m.id, 24),
                  checks=checks[:25], incidents=incidents,
                  chart_labels=[as_utc(c.checked_at).strftime("%H:%M:%S") for c in series],
                  chart_values=[c.response_ms for c in series],
                  chart_anoms=[c.is_anomaly for c in series])


@router.post("/dashboard/monitors/{monitor_id}/toggle")
def toggle_monitor(monitor_id: int, user: User | None = Depends(web_user),
                   db: Session = Depends(get_db)):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    m = _owned(db, user, monitor_id)
    if m:
        m.is_active = not m.is_active
        db.commit()
    return RedirectResponse(f"/dashboard/monitors/{monitor_id}", status_code=303)


@router.post("/dashboard/monitors/{monitor_id}/public")
def toggle_public(monitor_id: int, user: User | None = Depends(web_user),
                  db: Session = Depends(get_db)):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    m = _owned(db, user, monitor_id)
    if m:
        m.is_public = not m.is_public
        db.commit()
    return RedirectResponse(f"/dashboard/monitors/{monitor_id}", status_code=303)


@router.get("/status/{slug}")
def status_page(slug: str, request: Request, db: Session = Depends(get_db)):
    """Public, unauthenticated status page. Shows only monitors marked public,
    by NAME only (the monitored URL is never exposed)."""
    owner = db.scalar(select(User).where(User.status_slug == slug))
    if owner is None:
        raise HTTPException(404, "Status page not found")
    monitors = db.scalars(select(Monitor).where(
        Monitor.user_id == owner.id, Monitor.is_public.is_(True)).order_by(Monitor.id)).all()
    rows = [{"name": m.name, "status": stats.current_status(db, m),
             "uptime_24h": stats.uptime_percent(db, m.id, 24),
             "uptime_7d": stats.uptime_percent(db, m.id, 24 * 7),
             "avg_ms": stats.avg_response_ms(db, m.id, 24)} for m in monitors]
    names = {m.id: m.name for m in monitors}
    incidents = db.scalars(select(Incident).where(Incident.monitor_id.in_(list(names)))
                           .order_by(Incident.id.desc()).limit(10)).all() if names else []
    active = [r["status"] for r in rows if r["status"] != "paused"]
    overall = ("down" if "down" in active else "degraded" if "degraded" in active
               else "up" if "up" in active else "unknown")
    return render(request, "status.html", None, rows=rows, overall=overall,
                  incidents=[{"name": names[i.monitor_id], "i": i} for i in incidents])


@router.post("/dashboard/monitors/{monitor_id}/check")
def check_now(monitor_id: int, user: User | None = Depends(web_user),
              db: Session = Depends(get_db)):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    m = _owned(db, user, monitor_id)
    if m:
        record_result(db, m, run_check(m))
    return RedirectResponse(f"/dashboard/monitors/{monitor_id}", status_code=303)


@router.post("/dashboard/monitors/{monitor_id}/delete")
def delete_monitor(monitor_id: int, user: User | None = Depends(web_user),
                   db: Session = Depends(get_db)):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    m = _owned(db, user, monitor_id)
    if m:
        db.delete(m)
        db.commit()
    return RedirectResponse("/dashboard", status_code=303)
