import os
import re
import json
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from keybert import KeyBERT
from konlpy.tag import Okt

class ComprehensivePatentSearch:
    """하나의 특허 번호나 명칭으로 기본 정보, 인용/피인용, 패밀리 정보를 종합적으로 조회합니다."""
    def __init__(self, api_key):
        if not api_key:
            raise ValueError("API 키가 필요합니다.")
        self.api_key = "XEOuXi2dRDnOl9En6SmNGa6kEAvqw3QxogLm4iRNt1M="
        self.URLS = {
            "word_search": "http://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice/getWordSearch",
            "cited_info": "http://plus.kipris.or.kr/openapi/rest/CitationService/citationInfoV2",
            "citing_info": "http://plus.kipris.or.kr/openapi/rest/CitingService/citingInfo",
            "family_info": "http://plus.kipris.or.kr/kipo-api/kipi/patFamInfoSearchService/getAppNoPatFamInfoSearch"
        }

    def _make_request(self, url, params):
        try:
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                if root.find('.//item') is None: return None
                return root
            return None
        except Exception:
            return None

    def _get_app_number_from_title(self, title):
        print(f"--- 대표 특허 검색: '{title}' ---")
        params = {'word': title, 'ServiceKey': self.api_key}
        root = self._make_request(self.URLS["word_search"], params)
        if root is not None:
            item = root.find('.//item')
            app_num = item.findtext('applicationNumber')
            clean_app_num = app_num.replace("-", "") if app_num else None
            print(f"✅ 대표 출원번호 찾음: {clean_app_num}")
            return clean_app_num
        return None

    def get_basic_info(self, app_number):
        """출원번호로 기본 서지 정보를 동적으로 가져옵니다."""
        print("--- 1. 기본 정보 조회 중... ---")
        params = {'word': app_number, 'ServiceKey': self.api_key}
        root = self._make_request(self.URLS["word_search"], params)
        if root is not None:
            item = root.find('.//item')
            basic_info = {}
            for child in item:
                if child.text and child.text.strip():
                    basic_info[child.tag] = child.text.strip()
            return basic_info
        return {"error": "기본 정보를 가져오지 못했습니다."}

    def get_cited_info(self, app_number):
        print("--- 2. 인용문헌(이 특허가 참고한) 조회 중... ---")
        params = {'applicationNumber': app_number, 'accessKey': self.api_key}
        root = self._make_request(self.URLS["cited_info"], params)
        return [item.findtext('applicationNumber') for item in root.findall('.//citationInfoV2')] if root is not None else []

    def get_citing_info(self, app_number):
        print("--- 3. 피인용문헌(이 특허를 참고한) 조회 중... ---")
        params = {'standardCitationApplicationNumber': app_number, 'accessKey': self.api_key}
        root = self._make_request(self.URLS["citing_info"], params)
        return [item.findtext('applicationNumber') for item in root.findall('.//citingInfo')] if root is not None else []

    def get_family_info(self, app_number):
        print("--- 4. 해외 패밀리 특허 조회 중... ---")
        params = {'applicationNumber': app_number, 'ServiceKey': self.api_key}
        root = self._make_request(self.URLS["family_info"], params)
        family_list = []
        if root is not None:
            for item in root.findall('.//item'):
                family_list.append({
                    'country': item.findtext('applicationCountryCode'),
                    'app_number': item.findtext('applicationNumber'),
                })
        return family_list

    def search(self, query):
        if re.match(r'^\d+[\d-]*\d+$', query):
            app_number = query.replace("-", "")
            print(f"✅ 출원번호 '{app_number}'로 검색을 시작합니다.")
        else:
            app_number = self._get_app_number_from_title(query)

        if not app_number:
            return {"error": f"'{query}'에 해당하는 대표 특허를 찾을 수 없습니다."}

        basic_info = self.get_basic_info(app_number)
        if "error" in basic_info:
            return basic_info

        return {
            "main_patent_query": query,
            "applicationNumber": app_number,
            "basicInfo": basic_info,
            "citedPatents (이 특허가 참고)": self.get_cited_info(app_number),
            "citingPatents (이 특허를 참고)": self.get_citing_info(app_number),
            "patentFamily": self.get_family_info(app_number)
        }

class AIPatentAnalyst:
    """AI 모델로 키워드를 추출하고 종합적인 특허 정보를 분석하는 컨트롤러"""
    def __init__(self, service_key):
        model_name = "jhgan/ko-sroberta-multitask"
        self.keybert_model = KeyBERT(model_name)
        self.searcher = ComprehensivePatentSearch(api_key=service_key)
        self.okt = Okt()
        print("✅ AI 특허 분석기 초기화 완료.")

    def analyze(self, query_sentence):
        """자연어 문장을 입력받아 종합 특허 정보를 분석하여 반환합니다."""
        print(f"\n입력 문장: \"{query_sentence}\"")
        keywords_with_scores = self.keybert_model.extract_keywords(
            query_sentence, keyphrase_ngram_range=(1, 3), stop_words=None, top_n=10
        )
        if not keywords_with_scores:
            return {"error": "입력된 문장에서 핵심 기술 어구를 추출하지 못했습니다."}
        max_score = keywords_with_scores[0][1]
        threshold = max_score * 0.7
        selected_phrases = [kw for kw, score in keywords_with_scores if score >= threshold]
        print(f"▶ AI가 1차 추출한 핵심 어구 (점수 기반): {selected_phrases}")
        raw_keywords_text = " ".join(selected_phrases)
        filtered_nouns = self.okt.nouns(raw_keywords_text)
        unique_words = set(word for word in filtered_nouns if len(word) > 1)
        final_keyword = " ".join(sorted(list(unique_words), key=len, reverse=True))
        if not final_keyword:
             return {"error": "추출된 어구에서 유효한 키워드를 찾지 못했습니다."}
        print(f"▶ 최종 정제된 검색어: '{final_keyword}'")
        return self.searcher.search(final_keyword)

# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 이 함수가 수정되었습니다 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
def print_pretty_result(result: dict):
    """분석 결과를 보고서 형태로 예쁘게 출력하는 함수"""
    SEPARATOR = "─" * 60

    print("\n" + SEPARATOR)
    print("📜 최종 종합 정보 보고서 📜".center(50))
    print(SEPARATOR)

    if "error" in result:
        print(f"\n❌ 분석 실패: {result['error']}")
        print(SEPARATOR)
        return

    # --- 검색 정보 ---
    print("\n[ 🔍 검색 정보 ]")
    print(f"  - 최종 검색어: {result.get('main_patent_query', 'N/A')}")

    # --- 대표 특허 상세 정보 ---
    print("\n" + SEPARATOR)
    print("\n[ 📑 대표 특허 상세 정보 ]")
    basic_info = result.get("basicInfo", {})
    
    # --- 출력 순서를 제어하고, 동적으로 모든 정보를 출력 ---
    
    # 1. 화면에 표시할 정보의 순서와 그룹을 미리 정의
    display_groups = {
        "💡 핵심 정보": ['inventionTitle', 'astrtCont'],
        "🆔 주요 식별 정보": ['applicationNumber', 'registerNumber', 'publicationNumber', 'openNumber', 'applicantName'],
        "📅 주요 일자": ['applicationDate', 'publicationDate', 'registerDate', 'openDate'],
        "⚙️ 기타 정보": ['registerStatus', 'ipcNumber', 'drawing', 'bigDrawing']
    }

    # API 응답에 있는 모든 키를 추적하기 위한 집합
    remaining_keys = set(basic_info.keys())

    # 2. 정의된 순서와 그룹에 따라 정보 출력
    for group_name, keys_in_group in display_groups.items():
        # 해당 그룹에 출력할 정보가 있는지 확인
        has_content = any(key in basic_info for key in keys_in_group)
        if not has_content:
            continue

        print(f"\n{group_name}")
        for key in keys_in_group:
            if key in basic_info:
                KOREAN_LABELS = {
                    'inventionTitle': '발명의 명칭', 'applicationNumber': '출원번호', 'applicantName': '출원인',
                    'astrtCont': '요약', 'applicationDate': '출원일자', 'registerStatus': '현재 상태',
                    'publicationNumber': '공고번호', 'publicationDate': '공고일자', 'openNumber': '공개번호',
                    'openDate': '공개일자', 'registerNumber': '등록번호', 'registerDate': '등록일자',
                    'ipcNumber': 'IPC 분류', 'drawing': '대표도면 URL', 'bigDrawing': '큰 대표도면 URL'
                }
                label = KOREAN_LABELS.get(key, key)
                value = basic_info.get(key)
                
                if key == 'astrtCont':
                    print(f"  - {label}:\n    {value[:200]}...")
                else:
                    print(f"  - {label}: {value}")
                
                if key in remaining_keys:
                    remaining_keys.remove(key)

    # 3. 위에서 정의되지 않은 나머지 정보가 있다면 모두 출력 (유연성 확보)
    if remaining_keys:
        print("\n기타 추가 정보")
        for key in remaining_keys:
            print(f"  - {key}: {basic_info[key]}")


    # --- 관계 정보 (기존과 동일) ---
    print("\n" + SEPARATOR)
    print("\n[ 🔗 관계 특허 정보 ]")
    
    cited_patents = result.get("citedPatents (이 특허가 참고)", [])
    print(f"\n  - ➡️  이 특허가 인용한 특허: ", end="")
    if cited_patents:
        print(f"{len(cited_patents)}건")
        for patent in cited_patents: print(f"    - {patent or '번호 없음'}")
    else:
        print("정보 없음")

    citing_patents = result.get("citingPatents (이 특허를 참고)", [])
    print(f"\n  - ⬅️  이 특허를 인용한 특허: ", end="")
    if citing_patents:
        print(f"{len(citing_patents)}건")
        for patent in citing_patents: print(f"    - {patent or '번호 없음'}")
    else:
        print("정보 없음")

    patent_family = result.get("patentFamily", [])
    print(f"\n  - 🌐 해외 패밀리 특허: ", end="")
    if patent_family:
        print(f"{len(patent_family)}건")
        family_by_country = {}
        for patent in patent_family:
            country = patent.get('country', '?')
            if country not in family_by_country:
                family_by_country[country] = []
            family_by_country[country].append(patent.get('app_number', '번호 없음'))
        
        for country, numbers in family_by_country.items():
            print(f"    - [{country}]: {', '.join(list(set(numbers)))}")
    else:
        print("정보 없음")
    
    print("\n" + SEPARATOR)

load_dotenv()
KIPRIS_API_KEY = os.getenv("KIPRIS_API_KEY")
analyst = AIPatentAnalyst(service_key=KIPRIS_API_KEY)
