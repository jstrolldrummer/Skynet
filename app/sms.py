from twilio.rest import Client

from . import config


def get_client() -> Client:
    return Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)


def send_sms(to: str, body: str) -> str:
    msg = get_client().messages.create(
        from_=config.TWILIO_FROM_NUMBER,
        to=to,
        body=body,
    )
    return msg.sid
