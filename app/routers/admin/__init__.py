from fastapi import APIRouter

from .overview import router as overview_router
from .tasks import router as tasks_router
from .assign_task import router as assign_task_router
from .assignment_data import router as assignment_data_router
from .zones import router as zones_router
from .supervisors import router as supervisors_router
from .bwg_count import router as bwg_count_router
from .user import router as users_router
from .driver_locations import router as driver_locations_router
from .collection_data import router as collection_data_router
from .lookups import router as lookups_router
from .create_task import router as create_task_router


router = APIRouter()

router.include_router(users_router)
router.include_router(supervisors_router)
router.include_router(bwg_count_router)
router.include_router(overview_router)
router.include_router(lookups_router)
router.include_router(users_router)
router.include_router(tasks_router)
router.include_router(create_task_router)
router.include_router(assign_task_router)
router.include_router(assignment_data_router)
router.include_router(users_router)
router.include_router(zones_router)
router.include_router(driver_locations_router)
router.include_router(supervisors_router)
router.include_router(collection_data_router)
from .profile import router as profile_router
router.include_router(profile_router)
from .bwg_payment import router as bwg_payment_router
router.include_router(bwg_payment_router)
from .driver_photos import router as driver_photos_router
router.include_router(driver_photos_router)
