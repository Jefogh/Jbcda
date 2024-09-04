import base64
import cv2
import numpy as np
import httpx
import random
import flet as ft
from flet import (
    Page, Column, Row, Text, ElevatedButton, TextField, Image, FilePicker, AlertDialog, FilePickerResultEvent
)

class CaptchaApp:
    def __init__(self, page: Page):
        self.page = page
        self.page.title = "Captcha Solver"
        self.page.vertical_alignment = "start"
        
        self.accounts = {}
        self.background_images = []

        # Add Account and Upload Background buttons
        self.page.add(
            ElevatedButton(text="Add Account", on_click=self.add_account),
            ElevatedButton(text="Upload Backgrounds", on_click=self.upload_backgrounds)
        )
        self.page.update()

    def add_account(self, e):
        self.username_input = TextField(label="Enter Username", autofocus=True)
        self.password_input = TextField(label="Enter Password", password=True)
        self.dialog = AlertDialog(
            title=Text("Add Account"),
            content=Column([self.username_input, self.password_input]),
            actions=[
                ElevatedButton(text="Submit", on_click=self.on_account_submit)
            ]
        )
        self.page.dialog = self.dialog
        self.dialog.open = True
        self.page.update()

    def on_account_submit(self, e):
        username = self.username_input.value
        password = self.password_input.value

        if username and password:
            user_agent = self.generate_user_agent()
            session = self.create_session(user_agent)
            login_success = self.login(username, password, user_agent, session)
            if login_success:
                self.accounts[username] = {
                    'password': password,
                    'user_agent': user_agent,
                    'session': session,
                    'captcha_id1': None,
                    'captcha_id2': None
                }
                self.create_account_ui(username)
                self.dialog.open = False
                self.page.update()

    def create_account_ui(self, username):
        captcha_id1_input = TextField(label="Enter Captcha ID 1")
        captcha_id2_input = TextField(label="Enter Captcha ID 2")

        self.accounts[username]['captcha_id1'] = captcha_id1_input.value
        self.accounts[username]['captcha_id2'] = captcha_id2_input.value

        self.page.add(
            Row(
                [
                    Text(f"Account: {username}"),
                    captcha_id1_input,
                    captcha_id2_input,
                    ElevatedButton(text="Request All", on_click=lambda _: self.request_all_captchas(username)),
                ]
            )
        )
        self.page.update()

    def request_all_captchas(self, username):
        self.request_captcha(username, self.accounts[username]['captcha_id1'])
        self.request_captcha(username, self.accounts[username]['captcha_id2'])

    def upload_backgrounds(self, e):
        self.file_picker = FilePicker(on_result=self.on_background_selected)
        self.page.overlay.append(self.file_picker)
        self.file_picker.pick_files(allow_multiple=True)

    def on_background_selected(self, e: FilePickerResultEvent):
        if e.files:
            self.background_images = [cv2.imread(file.path) for file in e.files]
            self.page.snack_bar = ft.SnackBar(
                Text(f"{len(self.background_images)} background images uploaded successfully!"), open=True
            )
            self.page.update()

    def create_session(self, user_agent):
        session = httpx.Client(headers=self.generate_headers(user_agent))
        return session

    def login(self, username, password, user_agent, session, retry_count=3):
        login_url = 'https://api.ecsc.gov.sy:8080/secure/auth/login'
        login_data = {
            'username': username,
            'password': password
        }

        for attempt in range(retry_count):
            try:
                response = session.post(login_url, json=login_data)
                if response.status_code == 200:
                    return True
                elif response.status_code in {401, 402, 403}:
                    print(f"Error {response.status_code}. Retrying...")
                else:
                    return False
            except httpx.RequestError as e:
                print(f"Request error: {e}. Retrying...")
            except httpx.HTTPStatusError as e:
                print(f"HTTP status error: {e}. Retrying...")
            except Exception as e:
                print(f"Unexpected error: {e}. Retrying...")

        return False

    def request_captcha(self, username, captcha_id):
        session = self.accounts[username].get('session')

        if not session:
            print(f"No session found for user {username}")
            return

        captcha_data = self.get_captcha(session, captcha_id)
        if captcha_data:
            self.show_captcha(captcha_data, username, captcha_id)
        else:
            print(f"Failed to get captcha for {username}")

    def get_captcha(self, session, captcha_id):
        try:
            options_url = f"https://api.ecsc.gov.sy:8080/rs/reserve?id={captcha_id}&captcha=0"
            session.options(options_url)

            captcha_url = f"https://api.ecsc.gov.sy:8080/files/fs/captcha/{captcha_id}"
            response = session.get(captcha_url)

            if response.status_code == 200:
                response_data = response.json()
                if 'file' in response_data:
                    return response_data['file']
            return None
        except Exception as e:
            print(f"Failed to get captcha: {e}")
            return None

    def show_captcha(self, captcha_data, username, captcha_id):
        try:
            captcha_base64 = captcha_data.split(",")[1] if ',' in captcha_data else captcha_data
            captcha_image_data = base64.b64decode(captcha_base64)

            with open("captcha.jpg", "wb") as f:
                f.write(captcha_image_data)

            captcha_image = cv2.imread("captcha.jpg")
            processed_image = self.process_captcha(captcha_image)

            img = Image(src_base64=captcha_data, width=500, height=300)
            captcha_input = TextField(label="Enter Captcha", on_submit=lambda e: self.submit_captcha(username, captcha_id, captcha_input.value))

            self.page.add(img, captcha_input)
            self.page.update()

        except Exception as e:
            print(f"Error processing captcha data: {e}")

    def process_captcha(self, captcha_image):
        if not self.background_images:
            return captcha_image

        best_background = None
        min_diff = float('inf')

        for background in self.background_images:
            if background.shape != captcha_image.shape:
                background = cv2.resize(background, (captcha_image.shape[1], captcha_image.shape[0]))

            diff = cv2.absdiff(captcha_image, background)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            score = np.sum(gray_diff)

            if score < min_diff:
                min_diff = score
                best_background = background

        if best_background is not None:
            diff = cv2.absdiff(captcha_image, best_background)
            gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)

            kernel = np.ones((3, 3), np.uint8)
            cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

            return cleaned
        else:
            return captcha_image

    def submit_captcha(self, username, captcha_id, captcha_solution):
        session = self.accounts[username].get('session')

        get_url = f"https://api.ecsc.gov.sy:8080/rs/reserve?id={captcha_id}&captcha={captcha_solution}"
        get_response = session.get(get_url)

        if get_response.status_code == 200:
            print("Captcha solved successfully!")
        else:
            print(f"Failed to solve captcha for {username}")

    def generate_headers(self, user_agent):
        headers = {
            'User-Agent': user_agent,
            'Content-Type': 'application/json',
            'Source': 'WEB',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://ecsc.gov.sy/',
            'Origin': 'https://ecsc.gov.sy',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site'
        }
        return headers

    def generate_user_agent(self):
        user_agent_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36",
            "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36",
            "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36"
        ]
        return random.choice(user_agent_list)

def main(page: Page):
    app = CaptchaApp(page)

ft.app(target=main)
