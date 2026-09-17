from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    max_results_per_query: int = int(os.getenv("MAX_RESULTS_PER_QUERY", "6"))
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "20"))
    db_path: str = os.getenv("RISKWATCH_DB", "riskwatch_state.json")
    alert_threshold: int = int(os.getenv("ALERT_THRESHOLD", "70"))
SETTINGS = Settings()

CORE_TERMS = ("мобилизация","мобилизационная подготовка","призыв","контракт","осужденные","осуждённые","заключенные","заключённые","ФСИН","УФСИН","ФСИН России","военная служба","добровольцы","военный контракт","исправительные учреждения","колонии","СИЗО","перемещение осужденных","набор военнослужащих","добровольческое формирование","освобождение осужденных","замена наказания")

REGIONS = ["Адыгея","Алтай","Алтайский край","Амурская область","Архангельская область","Астраханская область","Башкортостан","Белгородская область","Брянская область","Бурятия","Владимирская область","Волгоградская область","Вологодская область","Воронежская область","Дагестан","Донецкая Народная Республика","Еврейская автономная область","Забайкальский край","Запорожская область","Ивановская область","Ингушетия","Иркутская область","Кабардино-Балкария","Калининградская область","Калмыкия","Калужская область","Камчатский край","Карачаево-Черкесия","Карелия","Кемеровская область — Кузбасс","Кировская область","Коми","Костромская область","Краснодарский край","Красноярский край","Крым","Курганская область","Курская область","Ленинградская область","Липецкая область","Луганская Народная Республика","Магаданская область","Марий Эл","Мордовия","Москва","Московская область","Мурманская область","Ненецкий автономный округ","Нижегородская область","Новгородская область","Новосибирская область","Омская область","Оренбургская область","Орловская область","Пензенская область","Пермский край","Приморский край","Псковская область","Ростовская область","Рязанская область","Самарская область","Санкт-Петербург","Саратовская область","Саха (Якутия)","Сахалинская область","Свердловская область","Севастополь","Северная Осетия — Алания","Смоленская область","Ставропольский край","Тамбовская область","Татарстан","Тверская область","Томская область","Тульская область","Тыва","Тюменская область","Удмуртия","Ульяновская область","Хабаровский край","Хакасия","Ханты-Мансийский автономный округ — Югра","Херсонская область","Челябинская область","Чечня","Чувашия","Чукотский автономный округ","Ямало-Ненецкий автономный округ","Ярославская область"]

SOURCE_TEMPLATES = [
    ("Президент России","site:kremlin.ru ({terms})"),
    ("Правительство России","site:government.ru ({terms})"),
    ("Минобороны России","site:mil.ru ({terms})"),
    ("ФСИН России","site:fsin.gov.ru ({terms})"),
    ("Минюст России","site:minjust.gov.ru ({terms})"),
    ("Генеральная прокуратура","site:epp.genproc.gov.ru ({terms})"),
    ("Госдума","site:duma.gov.ru ({terms})"),
    ("Совет Федерации","site:council.gov.ru ({terms})"),
    ("Официальное опубликование","site:publication.pravo.gov.ru ({terms})"),
    ("Закупки","site:zakupki.gov.ru ({terms})"),
    ("Росгвардия","site:rosguard.gov.ru ({terms})"),
    ("МВД России","site:mvd.ru ({terms})"),
    ("СК России","site:sledcom.ru ({terms})"),
    ("МЧС России","site:mchs.gov.ru ({terms})"),
    ("Reuters","site:reuters.com Russia ({terms})"),
    ("ТАСС","site:tass.ru ({terms})"),
    ("РИА Новости","site:ria.ru ({terms})"),
    ("Интерфакс","site:interfax.ru ({terms})"),
    ("РБК","site:rbc.ru ({terms})"),
    ("Коммерсантъ","site:kommersant.ru ({terms})"),
    ("Медиазона","site:zona.media ({terms})"),
    ("Telegram public","site:t.me ({terms})"),
    ("VK public","site:vk.com ({terms})"),
    ("YouTube public","site:youtube.com ({terms})")
]

REGIONAL_TEMPLATES = [
    ("Региональный УФСИН",'site:fsin.gov.ru "УФСИН" "{region}" ({terms})'),
    ("Региональный губернатор/правительство",'site:gov.ru "{region}" ({terms})'),
    ("Региональная прокуратура",'site:epp.genproc.gov.ru "{region}" ({terms})'),
    ("Региональные органы власти",'site:gov.ru "{region}" ({terms}) губернатор правительство'),
    ("Региональные закупки",'site:zakupki.gov.ru "{region}" ({terms})'),
    ("Региональные СМИ",'site:gov.ru "{region}" ({terms}) мобилизация ФСИН губернатор'),
    ("Региональные Telegram",'site:t.me "{region}" ({terms})'),
    ("Региональные VK",'site:vk.com "{region}" ({terms})'),
    ("Региональный YouTube",'site:youtube.com "{region}" ({terms})')
]

def build_queries():
    terms=' OR '.join(f'"{x}"' for x in CORE_TERMS)
    out=[(name,t.format(terms=terms)) for name,t in SOURCE_TEMPLATES]
    for region in REGIONS:
        for name,t in REGIONAL_TEMPLATES:
            out.append((f"{name}: {region}",t.format(region=region,terms=terms)))
    return out
