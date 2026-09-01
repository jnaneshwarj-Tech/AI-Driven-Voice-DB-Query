import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import settings

def send_reset_password_email(to_email: str, reset_link: str) -> bool:
    """
    Sends password reset link to user's registered email using SMTP.
    If SMTP credentials are not configured, logs the reset link to console for local dev.
    """
    subject = "Password Reset Request - AI Student DBMS"
    sender_email = settings.MAIL_FROM or settings.MAIL_USERNAME or "noreply@studentdbms.edu"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; margin: 0; padding: 20px; }}
            .container {{ max-width: 550px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 30px; box-shadow: 0 4px 15px rgba(0,0,0,0.08); border: 1px solid #e2e8f0; }}
            .header {{ text-align: center; border-bottom: 2px solid #3b82f6; padding-bottom: 15px; margin-bottom: 25px; }}
            .header h2 {{ color: #1e293b; margin: 0; font-size: 22px; }}
            .content {{ color: #334155; line-height: 1.6; font-size: 15px; }}
            .btn-wrapper {{ text-align: center; margin: 30px 0; }}
            .btn {{ background-color: #2563eb; color: #ffffff !important; padding: 12px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; display: inline-block; box-shadow: 0 4px 10px rgba(37,99,235,0.3); }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #94a3b8; text-align: center; border-top: 1px solid #f1f5f9; padding-top: 15px; }}
            .link-text {{ word-break: break-all; color: #2563eb; font-size: 13px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>🎓 AI Student Data Management System</h2>
            </div>
            <div class="content">
                <p>Hello,</p>
                <p>We received a request to reset the password for your account linked to <strong>{to_email}</strong>.</p>
                <p>Click the button below to set a new password. This link will expire in <strong>20 minutes</strong>.</p>
                <div class="btn-wrapper">
                    <a href="{reset_link}" class="btn" target="_blank">Reset My Password</a>
                </div>
                <p>If the button doesn't work, copy and paste this link into your web browser:</p>
                <p className="link-text"><a href="{reset_link}">{reset_link}</a></p>
                <p>If you did not request a password reset, please ignore this email. Your password will remain unchanged.</p>
            </div>
            <div class="footer">
                <p>This is an automated message. Please do not reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Always log reset link for easy local testing
    print(f"\n=======================================================")
    print(f"[PASSWORD RESET EMAIL DISPATCH]")
    print(f"To: {to_email}")
    print(f"Reset Link: {reset_link}")
    print(f"=======================================================\n")

    if not settings.MAIL_USERNAME or not settings.MAIL_PASSWORD:
        print("[EMAIL SERVICE] SMTP credentials not set in .env. Email printed to console.")
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = to_email

        msg.attach(MIMEText(html_content, "html"))

        server = smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT, timeout=10)
        if settings.MAIL_USE_TLS:
            server.starttls()
        server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        server.sendmail(sender_email, [to_email], msg.as_string())
        server.quit()
        print(f"[EMAIL SERVICE] Successfully sent reset email to {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL SERVICE WARNING] Failed to send SMTP email: {e}")
        return True
