import logging
from dataclasses import replace
from copy import copy

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.config.container import Container
from backend.app.config.dependencies import get_container
from backend.app.models.plan import PlanRequest
from backend.app.services.outing_plan import create_plan, options

router=APIRouter(tags=['outing plans'])
logger=logging.getLogger(__name__)


@router.get('/plans/options')
async def plan_options(container: Container=Depends(get_container)):
    return options(container.pets.places()['items'])


@router.post('/plans')
async def plan(payload: PlanRequest, request: Request, container: Container=Depends(get_container)):
    if not container.settings.api_key or not container.settings.model:
        raise HTTPException(503,'The outing planner is not configured yet.')
    try:
        async with container.llm_gate.slot(degraded=getattr(request.state,'rate_limited',False)) as full:
            if not full:
                container=copy(container)
                container.settings=replace(container.settings,model=container.settings.fallback_model)
            return await create_plan(container,payload)
    except TimeoutError as exc:
        raise HTTPException(503,'The outing planner is busy. Please try again shortly.') from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except Exception as exc:
        logger.exception('Outing planning failed')
        raise HTTPException(502,'The outing planner is temporarily unavailable. Please try again.') from exc
