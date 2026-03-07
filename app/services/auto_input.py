import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from undetected_chromedriver import Chrome, ChromeOptions
from app.config import Config

class AutoInput:
    def __init__(self, login: str, password: str, cookies=None):
        self.login = login
        self.password = password
        self.cookies = cookies

    def _init_driver(self):
        options = ChromeOptions()
        if Config.HEADLESS:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        self.driver = Chrome(options=options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    async def execute_task(self, url: str, answer: dict, task_data: dict,
                           allowed_errors: int = 0, target_duration: int = 30):
        self._init_driver()
        start = time.time()
        try:
            if self.cookies:
                self.driver.get("https://school.mos.ru")
                for name, value in self.cookies.items():
                    self.driver.add_cookie({"name": name, "value": value})
                self.driver.get(url)
            else:
                self._login()
                self.driver.get(url)

            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
            self._random_scroll()
            time.sleep(random.uniform(1, 2))

            options = task_data.get('options', [])
            wrongs = [opt['text'] for opt in options if opt['text'] != answer.get('text','')] if options else []
            if not wrongs and allowed_errors > 0:
                wrongs = [str(random.randint(1,100)) for _ in range(3)]

            for i in range(allowed_errors):
                if i > 0:
                    self.driver.get(url)
                    self._random_scroll()
                    time.sleep(random.uniform(1,2))
                self._fill_answer(wrongs[i % len(wrongs)], task_data)
                time.sleep(random.uniform(1,2))
                self._click_submit()
                time.sleep(random.uniform(2,4))

            if allowed_errors > 0:
                self.driver.get(url)
                self._random_scroll()
                time.sleep(random.uniform(1,2))
            self._fill_answer(answer['text'], task_data)
            time.sleep(random.uniform(1,2))
            self._click_submit()
            time.sleep(random.uniform(3,5))

            elapsed = time.time() - start
            if elapsed < target_duration:
                time.sleep(target_duration - elapsed)

            screenshot = self.driver.get_screenshot_as_png()
            return {"success": True, "screenshot": screenshot}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.driver.quit()

    def _login(self):
        self.driver.get("https://login.mos.ru")
        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.NAME, "login")))
        self.driver.find_element(By.NAME, "login").send_keys(self.login)
        time.sleep(random.uniform(0.3,0.7))
        self.driver.find_element(By.NAME, "password").send_keys(self.password)
        time.sleep(random.uniform(0.3,0.7))
        self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        WebDriverWait(self.driver, 10).until(EC.url_contains("school.mos.ru"))

    def _fill_answer(self, text: str, task_data: dict):
        ttype = task_data['task_type']
        if ttype == 'single_choice':
            labels = self.driver.find_elements(By.CSS_SELECTOR, "label.answer-option")
            for lbl in labels:
                if text in lbl.text:
                    lbl.click()
                    return
        elif ttype == 'input':
            inp = self.driver.find_element(By.CSS_SELECTOR, "input[type='text'], input[type='number'], textarea")
            inp.clear()
            for ch in text:
                inp.send_keys(ch)
                time.sleep(random.uniform(0.05,0.15))
        # другие типы опущены для краткости

    def _click_submit(self):
        self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']").click()

    def _random_scroll(self):
        self.driver.execute_script(f"window.scrollTo(0, {random.randint(100,500)});")
