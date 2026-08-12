from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from multiprocessing import Pool, freeze_support
from datetime import date # 올해 연도
import os
import signal
import time
import json
import argparse
from generate_config import *
import traceback


## 현재 연도와 학기 구분을 위함
now_year = date.today().year
now_month = date.today().month

## 학기 코드(sy.knu.ac.kr에서 불러올 때 필요함)
if(now_month == 2):
    semesterCode = "CMBS001400001"
else:
    semesterCode = "CMBS001400002"

# 전역 설정 변수 초기화
CONFIG = {}

# DEBUG INFO WARNING ERROR CRITICAL


def sleep_exit(sec):
    print(f"Closing in {sec} seconds...")
    time.sleep(sec)
    exit()


def loginSugang(browser, snum, id, passwd):
    ## Login
    ## 20260811 현재 수강신청 사이트에 맞게 수정함
    browser.get(CONFIG["general"]["sugang_url"])
    e = browser.find_element(By.ID, "stdno")
    e.send_keys(snum)
    e = browser.find_element(By.ID, "userId")
    e.send_keys(id)
    e = browser.find_element(By.ID, "pssrd")
    e.send_keys(passwd)
    e = browser.find_element(By.ID, "btn_login")
    e.click()

    ## Check if alert is present (which means login failure)
    try:
        WebDriverWait(browser, 0).until(expected_conditions.alert_is_present())
        alert = browser.switch_to.alert
        print("ERROR", "Login failure:", alert.text)
        alert.accept()
        return False
    except TimeoutException:
        print("INFO", "Login succeed")
        return True

# 20260811 현재 상황에 맞게 수정함
def getLecInfo(lecCode):
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=1000))

    # payload
    # sy.knu.ac.kr에서 강좌정보를 가져옵니다.
    # "sbjetDvnno"이 분반정보
    payload = {
    "search": {
        "estblYear": now_year,
        "estblSmstrSctcd": semesterCode,
        "sbjetCd": lecCode[0:8],
        "sbjetNm": "",
        "crgePrfssNm": "",
        "sbjetRelmCd": "",
        "sbjetSctcd": "",
        "estblDprtnCd": "",
        "rmtCrseYn": "",
        "rprsnLctreLnggeSctcd": "",
        "flplnCrseYn": "",
        "pstinNtnnvRmtCrseYn": "",
        "dgGbDstrcRmtCrseYn": "",
        "sugrdEvltnYn": "",
        "prctsExrmnYn": "",
        "gubun": "01",
        "isApi": "Y",
        "bldngSn": "",
        "bldngCd": "",
        "bldngNm": "",
        "lssnsLcttmUntcd": "",
        "sbjetSctcd2": "",
        "contents": lecCode[0:8],
        "lctreLnggeSctcd": "ko",
        "knuFtrDesigYn": "",
        "cltreHmntsCltreYn": "",
        "sdgCltreYn": "",
        "rltmCrseYn": "",
        "riseRmtCrseYn": "",
        "coRcgnnSbjetYn": "",
        "sbjetDvnno": lecCode[8:]
    }}


    # response = session.post(CONFIG["general"]["lecinfo_url"], data={
    response = session.post("https://knuin.knu.ac.kr/public/web/stddm/lsspr/syllabus/lectPlnInqr/selectListLectPlnInqr", json=payload)

    data = response.json()
    
    # 한글 출력 테스트
    # print(json.dumps(data, indent=4, ensure_ascii=False))

    if data.get("data") and len(data["data"]) > 0:
        lec_data = data["data"][0]
        res = {
            "subj_class_cde": lec_data.get("crseNo", "").replace("-", ""),
            "subj_nm": lec_data.get("sbjetNm"),
            "unit": int(lec_data.get("crdit", 0)),
            "prof_nm": lec_data.get("totalPrfssNm"),
            "lect_quota": int(lec_data.get("attlcPrscpCnt", 0)), # 수강정원
            "lect_req_cnt": int(lec_data.get("appcrCnt", 0)), # 수강신청인원
        }
    else:
        res = {
            "subj_class_cde": lecCode,
            "subj_nm": "Unknown",
            "unit": 0,
            "prof_nm": "Unknown",
            "lect_quota": 0,
            "lect_req_cnt": 0,
        }
    return res


def initializer():
    # Ignore SIGINT in child workers
    signal.signal(signal.SIGINT, signal.SIG_IGN)


if __name__ == "__main__":
    pool = None
    browser = None

    ## 소프트웨어특강(COMP0432001)으로 getLectInfo 디버깅
    '''
    getLecInfo("COMP0432001")
    exit()
    '''

    ### Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate_config", default=None, metavar="DEST_DIR")
    args = parser.parse_args()
    if args.generate_config:
        ## Generate config and exit
        generate_config(args.generate_config, "config.json")
        exit()

    try:
        ### Load config
        CONFIG = json.load(open("./config.json", "r"))
        print("VERBOSE", "Config loaded")

        ### Configure multiprocess pool, chromedriver
        freeze_support()
        pool = Pool(processes=CONFIG["general"]["pool_size"], initializer=initializer)
        # Use Selenium Manager (Selenium 4.6+) to automatically handle ChromeDriver
        browser = webdriver.Chrome()

        ### Login to sugang
        if not loginSugang(browser, **CONFIG["login"]):
            raise Exception("LoginFailureException")

        ### '꾸러미신청목록' 클릭
        e = browser.find_element(By.ID, "tabs2")
        e.click()

        ### Main loop
        # TODO - 꾸러미신청목록에 있는 강의들 순서대로 클릭하는 거 만들어야 됨
        # TODO - config.js에서 중요한 순서대로 강의가 입력된 걸로 간주해서 눌러지게 해야함
        # TODO - 정각 10분전에 자동으로 브라우저 로그인되게 한 다음, 정각에 신청 눌러지게 해야 함 (시간 기록해서 전공시간인지, 교양시간인지 체크)

        while True:
            ## Check remaining session time
            session_renew = CONFIG["general"]["session_renew"]  # remaining sec threshold
            try:
                e = browser.find_element(By.ID, "timeStatus")
                remain_sec = int(e.text.split("초")[0])
            except:
                remain_sec = 1200  # Initially it does not exist
                pass
            
            if remain_sec < session_renew:
                # Renew
                print("INFO", "Login renewing...")
                e = browser.find_element(By.CLASS_NAME, "stop")
                e.click()
                if not loginSugang(browser, **CONFIG["login"]):
                    raise Exception("LoginFailureException")
                
            print("VERBOSE", f"Remain {remain_sec}sec")
            
            ## Main logic
            regTable = browser.find_element(By.CSS_SELECTOR, "#onlineLectReqGrid > div.data > table > tbody")
            packTable = browser.find_element(By.CSS_SELECTOR, "#grid01")
            
            r = pool.map(getLecInfo, CONFIG["request"]["lectures"])
            
            ## sy.knu.ac.kr 테스트
            # print(r)
            # exit()


            """
            r.append({
                "subj_class_cde": "",
                "subj_nm": "Asdf",
                "unit": 3,
                "prof_nm": "sdf",
                "lect_quota": 80,
                "lect_req_cnt": 30,
            })
            """


            for lecInfo in r:
                print("VERBOSE", f"{lecInfo['subj_class_cde']}: r{lecInfo['lect_req_cnt']}, q{lecInfo['lect_quota']}")

                # If available (req_cnt < quota), find lecture in packTable
                if lecInfo["lect_req_cnt"] < lecInfo["lect_quota"]:
                    # Check if it's already registered
                    already = False
                    for tr in regTable.find_elements(By.TAG_NAME, "tr"):
                        td = tr.find_elements(By.TAG_NAME, "td")
                        if td and td[1].text == lecInfo["subj_class_cde"]:
                            print("WARNING", f"{lecInfo['subj_class_cde']}: Already registered")
                            already = True
                            break
                    if already:
                        continue

                    succeed = False
                    for tr in packTable.find_elements(By.TAG_NAME, "tr"):
                        td = tr.find_elements(By.TAG_NAME, "td")
                        if td and td[0].text == lecInfo["subj_class_cde"]:
                            try:
                                td[10].click()
                                WebDriverWait(browser, 0).until(expected_conditions.alert_is_present())
                                alert = browser.switch_to.alert
                                print("INFO", f"{lecInfo['subj_class_cde']}: {alert.text}")
                                alert.accept()
                                succeed = True
                            except TimeoutException:
                                print("INFO", "no alert")
                    if not succeed:
                        print("ERROR", "Not found in packTable")
                else:
                    continue
            time.sleep(CONFIG["general"]["delay_sec"])

    except KeyboardInterrupt:
        print("KeyboardInterrupt")
    except Exception as e:
        print(e)
        traceback.print_exc()
    finally:
        print("Terminating")
        if pool:
            pool.terminate()
            pool.join()
        if browser:
            browser.close()

        sleep_exit(3)
