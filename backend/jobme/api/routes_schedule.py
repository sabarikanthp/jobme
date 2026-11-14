from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from jobme.config.settings import load_settings, save_settings
from jobme.db.models import Run
from jobme.scheduling import windows_task as wt

router = APIRouter()


class ScheduleIn(BaseModel):
    days: list[str]
    times: list[str]
    wake: bool = False


def _runner(request: Request) -> wt.Runner:
    return getattr(request.app.state, "schedule_runner", wt.default_runner)


def _last_run(request: Request) -> dict | None:
    with Session(request.app.state.engine) as session:
        run = session.exec(select(Run).where(Run.trigger == "schedule")
                           .order_by(Run.started_at.desc(), Run.id.desc())).first()
        if run is None:
            return None
        return {"started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "found": run.found, "new": run.new, "matched": run.matched,
                "errors": list(run.errors or [])}


@router.get("/schedule")
def get_schedule(request: Request) -> dict:
    settings = load_settings(request.app.state.data_dir)
    out = wt.status(_runner(request))  # what Windows says, not what was saved
    return {**out, "days": list(settings.schedule.days), "times": list(settings.schedule.times),
            "wake": settings.schedule.wake, "last_run": _last_run(request)}


@router.post("/schedule/on")
def turn_on(body: ScheduleIn, request: Request) -> dict:
    command, arguments = wt.run_command(str(request.app.state.data_dir))
    try:
        xml = wt.build_task_xml(body.days, body.times, command, arguments, body.wake)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    data_dir = request.app.state.data_dir
    settings = load_settings(data_dir)
    settings.schedule.days = [d for d in body.days if d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]
    settings.schedule.times = list(body.times)
    settings.schedule.wake = body.wake
    save_settings(data_dir, settings)
    try:
        wt.register(xml, _runner(request))
    except wt.SchedulerError as e:
        raise HTTPException(400, str(e)) from None
    settings.schedule.enabled = True
    save_settings(data_dir, settings)
    return {"enabled": True}


@router.post("/schedule/off")
def turn_off(request: Request) -> dict:
    try:
        wt.unregister(_runner(request))
    except wt.SchedulerError as e:
        raise HTTPException(400, str(e)) from None
    data_dir = request.app.state.data_dir
    settings = load_settings(data_dir)
    settings.schedule.enabled = False
    save_settings(data_dir, settings)
    return {"enabled": False}
