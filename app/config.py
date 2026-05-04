import os

from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")
TASK_TOKEN = os.environ.get("TASK_TOKEN", "change-me")
DATABASE_PATH = os.environ.get("DATABASE_PATH", "./skynet.db")

COMPANY_NAME = os.environ.get("COMPANY_NAME", "Gray Custom Homes")
SENDER_NAME = os.environ.get("SENDER_NAME", "Wyatt")
