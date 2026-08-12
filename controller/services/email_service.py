import smtplib
import ssl
from email.message import EmailMessage
from config.settings import settings

def send_email(subject: str, body: str, to: str = None):
    to_email = to or settings.alert_email_to
    
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = settings.email_from
    msg['To'] = to_email

    try:
        # 默认使用 SSL (如果端口是 465) 或 STARTTLS (如果端口是 587)
        # 显式设置连接超时，避免 SMTP 无响应时无限阻塞（此前会导致 async 事件循环卡死）
        if settings.smtp_port == 465:
            server = smtplib.SMTP_SSL(
                settings.smtp_server,
                settings.smtp_port,
                timeout=settings.smtp_timeout,
                context=ssl.create_default_context(),
            )
        else:
            server = smtplib.SMTP(
                settings.smtp_server,
                settings.smtp_port,
                timeout=settings.smtp_timeout,
            )
            server.starttls(context=ssl.create_default_context())
            
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)
        server.quit()
        print(f"Successfully sent email to {to_email}: {subject}")
    except Exception as e:
        print(f"Failed to send email: {e}")
