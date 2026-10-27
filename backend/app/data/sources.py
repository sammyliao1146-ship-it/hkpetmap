from dataclasses import dataclass
from backend.app.data.google_cuisines import EXTRA_CUISINES

CATEGORIES = {
    'restaurants': '狗友善餐廳', 'parks': '一般公園', 'pet_parks': '寵物公園',
    'inclusive_parks': '寵物共享公園', 'vets': '獸醫診所／動物醫院',
    'hotels': '持牌寵物寄養所', 'transport': '攜寵交通',
    'management': '動物管理／注射中心', 'malls': '寵物友善商場',
}
CUISINES = ['咖啡／輕食', '中式', '港式', '日式', '韓式', '西式', '意式／薄餅', '泰式', '越式', '甜品', '素食', *EXTRA_CUISINES, '未分類']
FEHD_URL = 'https://www.fehd.gov.hk/tc_chi/licensing/dog_restaurants/dog_restaurants_list.html'
FEHD_DATA = 'https://www.fehd.gov.hk/english/licensing/dog_restaurants/getData.php'
HOTEL_URL = 'https://www.pets.gov.hk/tc_chi/animal_business/pet_hotel_list.html'
HOTEL_DATA = 'https://www.pets.gov.hk/js/pet_hotel.js'
VET_URL = 'https://www.pets.gov.hk/tc_chi/animal_health_and_welfare/vet_clinics_list.html'
SPCA_URL = 'https://www.spca.org.hk/animal-care-services/dog-behaviour-and-training/dog-behaviour-training-courses/'
AFCD_COURSES = 'https://www.pets.gov.hk/tc_chi/publications_and_downloads/service_booking/dog-training-courses.html'


@dataclass(frozen=True)
class Layer:
    key: str
    dataset: str
    category: str
    policy: str

    @property
    def url(self):
        return f'https://portal.csdi.gov.hk/server/rest/services/common/{self.dataset}/FeatureServer/0/query'


LAYERS = (
    Layer('pet_parks', 'lcsd_rcd_1670384486075_71092', 'pet_parks', 'dogs_permitted'),
    Layer('inclusive_parks', 'lcsd_rcd_1670384557490_22821', 'inclusive_parks', 'designated_area'),
    Layer('parks', 'lcsd_rcd_1629267205215_19292', 'parks', 'unknown'),
    Layer('management', 'afcd_rcd_1728896702834_67978', 'management', 'conditional'),
)
RESTAURANT_LAYER = Layer('restaurant_coordinates', 'fehd_rcd_1630036390312_58893', 'restaurants', 'dogs_permitted')
