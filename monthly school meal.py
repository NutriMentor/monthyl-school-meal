import streamlit as st
import requests
import re
import calendar
from datetime import datetime
import urllib3

# SSL 경고 메시지 비활성화
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- API 키 설정 ---
# st.secrets를 통해 배포 환경의 비밀값을 안전하게 가져옵니다.
try:
    API_KEY = st.secrets["NEIS_API_KEY"]
except FileNotFoundError:
    st.error("API 키가 설정되지 않았습니다. Streamlit Secrets에 NEIS_API_KEY를 추가해주세요.")
    st.stop()


# 전국 시/도 교육청 코드
OFFICE_CODES = {
    "서울특별시교육청": "B10", "부산광역시교육청": "C10", "대구광역시교육청": "D10",
    "인천광역시교육청": "E10", "광주광역시교육청": "F10", "대전광역시교육청": "G10",
    "울산광역시교육청": "H10", "세종특별자치시교육청": "I10", "경기도교육청": "J10",
    "강원도교육청": "K10", "충청북도교육청": "M10", "충청남도교육청": "N10",
    "전라북도교육청": "P10", "전라남도교육청": "Q10", "경상북도교육청": "R10",
    "경상남도교육청": "S10", "제주특별자치도교육청": "T10"
}

# --- Helper 함수들 ---
def search_schools(school_name, office_code):
    URL = (
        f"https://open.neis.go.kr/hub/schoolInfo"
        f"?KEY={API_KEY}&Type=json&pIndex=1&pSize=1000"
        f"&ATPT_OFCDC_SC_CODE={office_code}&SCHUL_NM={school_name}"
    )
    school_list = []
    try:
        response = requests.get(URL, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
        if 'schoolInfo' in data and 'row' in data['schoolInfo'][1]:
            for s in data['schoolInfo'][1]['row']:
                school_list.append({
                    'name': s['SCHUL_NM'],
                    'code': s['SD_SCHUL_CODE'],
                    'addr': s['ORG_RDNMA']
                })
        return school_list
    except Exception:
        return []

def fetch_monthly_menu(school_code, office_code, year, month, meal_code):
    start_date = f"{year}{month:02d}01"
    last_day = calendar.monthrange(year, month)[1]
    end_date = f"{year}{month:02d}{last_day}"
    URL = (
        f"https://open.neis.go.kr/hub/mealServiceDietInfo"
        f"?KEY={API_KEY}&Type=json&pIndex=1&pSize=100"
        f"&ATPT_OFCDC_SC_CODE={office_code}&SD_SCHUL_CODE={school_code}"
        f"&MMEAL_SC_CODE={meal_code}"
        f"&MLSV_FROM_YMD={start_date}&MLSV_TO_YMD={end_date}"
    )
    monthly_menu_data = {}
    try:
        response = requests.get(URL, timeout=15, verify=False)
        response.raise_for_status()
        data = response.json()
        if 'mealServiceDietInfo' in data and 'row' in data['mealServiceDietInfo'][1]:
            for record in data['mealServiceDietInfo'][1]['row']:
                date_key = record['MLSV_YMD']
                dish_info = record.get('DDISH_NM', '')
                dishes = [d.strip() for d in dish_info.split('<br/>') if d.strip()]
                monthly_menu_data[date_key] = dishes
        return monthly_menu_data
    except requests.exceptions.RequestException as e:
        st.error(f"급식 API 요청 중 오류가 발생했습니다: {e}")
        return None
    except Exception:
        return {}


# 학사일정 정보를 가져오는 함수 (안정성 및 데이터 포괄성 개선)
def fetch_school_schedule(school_code, office_code, year, month):
    start_date = f"{year}{month:02d}01"
    last_day = calendar.monthrange(year, month)[1]
    end_date = f"{year}{month:02d}{last_day}"
    URL = (
        f"https://open.neis.go.kr/hub/SchoolSchedule"
        f"?KEY={API_KEY}&Type=json&pIndex=1&pSize=100"
        f"&ATPT_OFCDC_SC_CODE={office_code}&SD_SCHUL_CODE={school_code}"
        f"&AA_FROM_YMD={start_date}&AA_TO_YMD={end_date}"
    )
    schedule_data = {}
    try:
        response = requests.get(URL, timeout=15, verify=False)
        response.raise_for_status()
        data = response.json()

        # API가 'SchoolSchedule' 키를 포함하고 있는지 확인
        if 'SchoolSchedule' in data:
            schedule_info = data['SchoolSchedule']

            # 행(row) 데이터가 실제로 존재하는지 확인 (보통 두 번째 요소에 위치)
            if len(schedule_info) > 1 and 'row' in schedule_info[1]:
                for record in schedule_info[1]['row']:
                    date_key = record.get('AA_YMD')
                    event_name = record.get('EVENT_NM', '').strip()
                    day_type_name = record.get('SBTR_DD_SC_NM', '').strip()

                    # 최종적으로 표시할 이벤트 텍스트 결정
                    display_text = ""
                    if event_name:
                        display_text = event_name
                    # 행사명이 없더라도 '수업일'이 아닌 특별한 날(예: 휴업일)은 표시
                    elif day_type_name and day_type_name != "수업일":
                        display_text = day_type_name

                    if date_key and display_text:
                        # 같은 날짜에 여러 이벤트가 있으면 쉼표로 연결
                        if date_key in schedule_data:
                            if display_text not in schedule_data[date_key]:
                                schedule_data[date_key] += f", {display_text}"
                        else:
                            schedule_data[date_key] = display_text
        return schedule_data
    except requests.exceptions.RequestException as e:
        st.error(f"학사일정 API 요청 중 오류가 발생했습니다: {e}")
        return {}
    except Exception:
        # JSON 파싱 오류 등이 발생해도 앱이 멈추지 않도록 빈 데이터 반환
        return {}


def create_calendar_html(school_name, year, month, menu_data, schedule_data, meal_name, show_allergy=True, saturday_has_menu=False, sunday_has_menu=False):
    cal = calendar.Calendar(firstweekday=6)
    month_days = cal.monthdatescalendar(year, month)

    # 너비 계산 로직
    narrow_col_width = 4
    num_narrow_cols = 0
    if not saturday_has_menu: num_narrow_cols += 1
    if not sunday_has_menu: num_narrow_cols += 1

    num_wide_cols = 7 - num_narrow_cols
    total_wide_width = 100 - (num_narrow_cols * narrow_col_width)

    if num_wide_cols > 0:
        wide_col_width = total_wide_width / num_wide_cols
    else:
        wide_col_width = narrow_col_width

    sun_width = narrow_col_width if not sunday_has_menu else wide_col_width
    sat_width = narrow_col_width if not saturday_has_menu else wide_col_width
    weekday_width = wide_col_width

    html = f"""
    <style>
        .calendar-container {{ font-family: 'Malgun Gothic', sans-serif; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1); background: #fff; }}
        .calendar-header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; text-align: center; font-size: 24px; font-weight: bold; }}
        .calendar-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
        .calendar-table th {{ padding: 10px; text-align: center; font-size: 14px; background-color: #f8f9ff; border: 1px solid #e9e9e9; }}
        .calendar-table td {{ min-height: 120px; padding: 8px; border: 1px solid #e9e9e9; vertical-align: top; word-break: break-all; }}
        .day-number {{ font-weight: bold; font-size: 14px; margin-bottom: 5px; }}
        .sunday .day-number {{ color: #e74c3c; }}
        .saturday .day-number {{ color: #3498db; }}
        .other-month {{ background-color: #f5f5f5; color: #ccc; }}
        .empty-weekend {{ background-color: #f8f9fa; opacity: 0.7; }}
        .empty-weekend .day-number {{ color: #b0b0b0; }}
        .menu-list {{ list-style: none; padding: 0; margin: 0; font-size: 12.5px; }}
        .menu-item {{ background-color: rgba(102, 126, 234, 0.08); border-radius: 4px; padding: 5px 7px; margin-bottom: 4px; line-height: 1.3; }}
        .allergy-info {{ font-size: 11px; color: #e74c3c; margin-left: 4px; }}
        .long-menu-name {{ font-size: 11px; font-weight: 500; }}

        /* 학사일정 스타일 */
        .event-name {{
            font-size: 11.5px;
            font-weight: bold;
            background-color: #e8f5e9; /* 연한 녹색 */
            color: #2e7d32;
            padding: 3px 6px;
            border-radius: 4px;
            margin-bottom: 5px;
            display: inline-block;
            max-width: 100%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        @media (max-width: 768px) {{
            .calendar-header {{ font-size: 18px; padding: 12px; }}
            .calendar-table th {{ font-size: 12px; padding: 8px 4px; }}
            .calendar-table td {{ padding: 4px; min-height: 100px; }}
            .day-number {{ font-size: 12px; }}
            .menu-list {{ font-size: 11px; }}
            .menu-item {{ padding: 4px 5px; }}
            .event-name {{ font-size: 10px; padding: 2px 4px; }}
        }}
    </style>
    """
    html += f"""
    <div class="calendar-container">
        <div class="calendar-header">{school_name} {year}년 {month}월 {meal_name} 식단</div>
        <table class="calendar-table">
            <thead>
                <tr>
                    <th style="color: #e74c3c; width: {sun_width}%;">일</th>
                    <th style="width: {weekday_width}%;">월</th>
                    <th style="width: {weekday_width}%;">화</th>
                    <th style="width: {weekday_width}%;">수</th>
                    <th style="width: {weekday_width}%;">목</th>
                    <th style="width: {weekday_width}%;">금</th>
                    <th style="color: #3498db; width: {sat_width}%;">토</th>
                </tr>
            </thead>
            <tbody>
    """
    for week in month_days:
        html += "<tr>"
        for day in week:
            date_key = day.strftime('%Y%m%d')
            day_class_list = []

            is_weekend = day.weekday() in [5, 6]
            has_menu = date_key in menu_data
            if is_weekend and not has_menu: day_class_list.append("empty-weekend")
            if day.weekday() == 6: day_class_list.append("sunday")
            elif day.weekday() == 5: day_class_list.append("saturday")

            day_class = " ".join(day_class_list)

            if day.month != month:
                html += f'<td class="other-month"><div class="day-number">{day.day}</div></td>'
                continue

            # 학사일정 HTML 생성
            schedule_html = ""
            if date_key in schedule_data:
                event = schedule_data[date_key]
                schedule_html = f'<div class="event-name" title="{event}">🗓️ {event}</div>'

            menu_html = ""
            if has_menu:
                menu_html += '<ul class="menu-list">'
                for item_raw in menu_data[date_key]:
                    match = re.match(r'^(.*?)\s*\(([\d\.]+)\)$', item_raw)
                    if match:
                        dish_name = match.group(1).strip()
                        allergy_info = match.group(2).strip()
                        dish_name_html = f'<span class="long-menu-name">{dish_name}</span>' if len(dish_name) > 10 else dish_name
                        menu_item_content = dish_name_html
                        if show_allergy:
                            menu_item_content += f'<span class="allergy-info">({allergy_info})</span>'
                    else:
                        menu_item_content = f'<span class="long-menu-name">{item_raw}</span>' if len(item_raw) > 10 else item_raw
                    menu_html += f'<li class="menu-item">{menu_item_content}</li>'
                menu_html += '</ul>'

            html += f'<td class="{day_class}"><div class="day-number">{day.day}</div>{schedule_html}{menu_html}</td>'
        html += "</tr>"

    html += "</tbody></table></div>"
    return html

# --- Streamlit UI ---
st.set_page_config(page_title="학교 급식 식단표", layout="wide")

st.markdown("""
<style>
    [data-testid="stSidebarNav"] button {
        background-color: #667eea; border: 1px solid #667eea; border-radius: 50%;
        color: white; transform: scale(1.2); transition: all 0.2s ease-in-out;
    }
    [data-testid="stSidebarNav"] button:hover {
        background-color: #764ba2; border: 1px solid #764ba2; transform: scale(1.3);
    }
    @media (max-width: 768px) { .main-title { font-size: 1.8rem !important; } }
</style>
<h1 class="main-title" style="text-align: center; color: #2c3e50; margin-bottom: 2rem; font-size: 2.5rem; font-weight: bold;">
    🗓️ 학교 급식 식단표
</h1>
""", unsafe_allow_html=True)

# --- Session State 초기화 ---
if 'school_list' not in st.session_state: st.session_state.school_list = []
if 'selected_school_code' not in st.session_state: st.session_state.selected_school_code = None
if 'selected_school_name' not in st.session_state: st.session_state.selected_school_name = None
if 'selected_month' not in st.session_state: st.session_state.selected_month = datetime.now().month

# --- 모든 컨트롤을 사이드바로 이동 ---
with st.sidebar:
    st.header("⚙️ 검색 설정")
    st.markdown("---")

    office_list = list(OFFICE_CODES.keys())
    default_office_index = office_list.index("강원도교육청")
    selected_office_name = st.selectbox("🏢 교육청을 선택하세요", options=office_list, index=default_office_index)
    selected_office_code = OFFICE_CODES[selected_office_name]

    school_search_keyword = st.text_input("🏫 학교 이름을 입력하세요", placeholder="전체 목록은 비워두고 검색")

    if st.button("학교 검색", use_container_width=True):
        st.session_state.school_list = search_schools(school_search_keyword, selected_office_code)

        if st.session_state.school_list:
            first_school = st.session_state.school_list[0]
            st.session_state.selected_school_code = first_school['code']
            st.session_state.selected_school_name = first_school['name']
        else:
            st.session_state.selected_school_code = None
            st.session_state.selected_school_name = None
            st.warning("검색 결과가 없습니다.")

    if st.session_state.school_list:
        display_names = [f"{s['name']} ({s['addr']})" for s in st.session_state.school_list]

        default_index = 0
        if st.session_state.selected_school_code:
            try:
                selected_school_object = next(s for s in st.session_state.school_list if s['code'] == st.session_state.selected_school_code)
                full_display_name = f"{selected_school_object['name']} ({selected_school_object['addr']})"
                default_index = display_names.index(full_display_name)
            except (StopIteration, ValueError):
                default_index = 0

        selected_display_name = st.selectbox(
            "🔎 검색된 학교 중 하나를 선택하세요",
            options=display_names,
            index=default_index,
            placeholder="학교를 선택해주세요."
        )

        if selected_display_name:
            selected_school = next((s for s in st.session_state.school_list if f"{s['name']} ({s['addr']})" == selected_display_name), None)
            if selected_school:
                st.session_state.selected_school_code = selected_school['code']
                st.session_state.selected_school_name = selected_school['name']

    st.markdown("---")

    if st.session_state.selected_school_name:
        current_year = datetime.now().year
        year = st.selectbox("📅 년", options=range(current_year - 5, current_year + 6), index=5)

        st.write("📅 월")
        month_cols = st.columns(3)
        for i in range(12):
            month_num = i + 1
            with month_cols[i % 3]:
                is_selected = (st.session_state.selected_month == month_num)
                if st.button(f"{month_num}월", type="primary" if is_selected else "secondary", use_container_width=True, key=f"month_{month_num}"):
                    st.session_state.selected_month = month_num

        st.markdown("---")
        meal_options = {"조식": "1", "중식": "2", "석식": "3"}
        selected_meal_name = st.radio("🍽️ 식사 구분", options=list(meal_options.keys()), index=1, horizontal=True)
        selected_meal_code = meal_options[selected_meal_name]
        show_allergy_info = st.toggle("알레르기 정보 표시", value=False)
    else:
        st.info("학교를 먼저 검색하고 선택해주세요.")

# --- 메인 화면의 조회 로직 ---
if st.session_state.selected_school_name:
    with st.spinner(f"{st.session_state.selected_school_name}의 식단 및 학사일정 정보를 불러오는 중입니다..."):
        # API를 통해 한 달치 메뉴 데이터를 가져옴
        monthly_menus = fetch_monthly_menu(
            st.session_state.selected_school_code,
            selected_office_code,
            year,
            st.session_state.selected_month,
            selected_meal_code
        )

        # API를 통해 한 달치 학사일정 데이터를 가져옴
        monthly_schedules = fetch_school_schedule(
            st.session_state.selected_school_code,
            selected_office_code,
            year,
            st.session_state.selected_month
        )

        saturday_has_menu = False
        sunday_has_menu = False
        if monthly_menus:
            for date_key in monthly_menus.keys():
                try:
                    day_of_week = datetime.strptime(date_key, '%Y%m%d').weekday()
                    if day_of_week == 5: saturday_has_menu = True
                    elif day_of_week == 6: sunday_has_menu = True
                    if saturday_has_menu and sunday_has_menu: break
                except ValueError:
                    continue

        if monthly_menus is None:
            st.error("데이터를 불러오는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
        # 식단과 학사일정이 모두 없는 경우에만 메시지 표시
        elif not monthly_menus and not monthly_schedules:
            st.warning(f"😭 **{st.session_state.selected_school_name}**의 **{year}년 {st.session_state.selected_month}월**에는 식단 및 학사일정 정보가 없습니다.")
        else:
            # 위에서 가져온 학사일정 정보를 함수에 전달
            calendar_view = create_calendar_html(
                st.session_state.selected_school_name,
                year, st.session_state.selected_month,
                monthly_menus,
                monthly_schedules, # 학사일정 데이터 전달
                selected_meal_name,
                show_allergy_info,
                saturday_has_menu=saturday_has_menu,
                sunday_has_menu=sunday_has_menu
            )
            st.markdown(calendar_view, unsafe_allow_html=True)
# --- 하단 정보 섹션 ---
st.markdown("---")
with st.expander("📌 알레르기 정보 안내 (펼쳐보기)"):
    st.markdown("**메뉴 옆의 숫자는 알레르기를 유발할 수 있는 식품을 의미합니다.**")
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.markdown("- `1`. 난류\n- `2`. 우유\n- `3`. 메밀\n- `4`. 땅콩\n- `5`. 대두")
    with col2: st.markdown("- `6`. 밀\n- `7`. 고등어\n- `8`. 게\n- `9`. 새우\n- `10`. 돼지고기")
    with col3: st.markdown("- `11`. 복숭아\n- `12`. 토마토\n- `13`. 아황산류\n- `14`. 호두\n- `15`. 닭고기")
    with col4: st.markdown("- `16`. 쇠고기\n- `17`. 오징어\n- `18`. 조개류\n- `19`. 잣")
    st.markdown("<div style='text-align: right; margin-top: 10px;'><small>*이 정보는 식품의약품안전처 고시에 따른 것입니다.*</small></div>", unsafe_allow_html=True)

st.info("📌 이 서비스는 나이스 교육정보 개방 포털의 API를 활용하여 제작되었습니다.")
st.markdown("""
<div style="text-align: center; color: #7f8c8d; margin-top: 2rem; font-size: 14px;">
    <p>🍚 학교 급식 식단표| Made by 영양교사 권영우</p>
</div>
""", unsafe_allow_html=True)