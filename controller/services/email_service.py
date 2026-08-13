import smtplib
import ssl
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from config.settings import settings


def _send(msg):
    """内部：发送 EmailMessage 对象（SMTP 连接/认证/发送）。"""
    try:
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
        print(f"Successfully sent email: {msg['Subject']}")
    except Exception as e:
        print(f"Failed to send email: {e}")


def send_email(subject: str, body: str, to: str = None):
    """发送纯文本邮件。"""
    to_email = to or settings.alert_email_to

    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = settings.email_from
    msg['To'] = to_email

    _send(msg)


def send_html_email(subject: str, html_body: str, images: dict = None, to: str = None):
    """发送 HTML 邮件，支持内嵌图片。

    Args:
        subject: 邮件主题
        html_body: HTML 正文
        images: {cid: png_bytes}，HTML 中以 <img src="cid:xxx"> 引用
        to: 收件人，默认 settings.alert_email_to
    """
    to_email = to or settings.alert_email_to

    # 标准 MIME 结构：multipart/related > [multipart/alternative > (plain, html)] + inline images
    # 这样不支持 HTML 的客户端退化为纯文本，支持 HTML 的客户端正常渲染内嵌图
    root = MIMEMultipart('related')
    root['Subject'] = subject
    root['From'] = settings.email_from
    root['To'] = to_email

    alt = MIMEMultipart('alternative')
    # 纯文本 fallback：HTML 邮件在内嵌图片无法显示时保证内容仍可读
    alt.attach(MIMEText("本邮件为 HTML 格式，请使用支持 HTML 的邮件客户端查看。", 'plain', 'utf-8'))
    alt.attach(MIMEText(html_body, 'html', 'utf-8'))
    root.attach(alt)

    if images:
        for cid, data in images.items():
            img = MIMEImage(data, 'png')
            img.add_header('Content-ID', f'<{cid}>')
            img.add_header('Content-Disposition', 'inline', filename=f'{cid}.png')
            root.attach(img)

    _send(root)