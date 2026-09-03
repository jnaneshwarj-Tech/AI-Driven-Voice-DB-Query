# 📧 Production Email Setup Guide

## Current Status
✅ **Dev Mode Working**: OTP prints to console when email credentials are not configured  
🎯 **Next Step**: Configure production email for real-world delivery

---

## 🚀 Step-by-Step Production Setup

### Option 1: Gmail (Recommended for College/Institution)

#### Step 1: Enable 2-Step Verification
1. Go to your Google Account: https://myaccount.google.com
2. Click **Security** in the left sidebar
3. Under "How you sign in to Google", click **2-Step Verification**
4. Follow the setup wizard to enable it

#### Step 2: Generate Gmail App Password
1. Go to: https://myaccount.google.com/apppasswords
2. You may be asked to sign in again
3. In the "Select app" dropdown, choose **Mail**
4. In the "Select device" dropdown, choose **Other (Custom name)**
5. Type: `AI Database Automator`
6. Click **Generate**
7. **Copy the 16-character password** (looks like: `abcd efgh ijkl mnop`)
   - Remove all spaces: `abcdefghijklmnop`
   - You'll use this in `.env` file

#### Step 3: Update Backend `.env` File
```bash
# Open backend/.env and update these lines:

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true

# Replace with your Gmail address
MAIL_USERNAME=your_college_email@gmail.com

# Paste the 16-character App Password (NO SPACES)
MAIL_PASSWORD=abcdefghijklmnop

# Sender configuration (can be same as MAIL_USERNAME)
MAIL_FROM=your_college_email@gmail.com
MAIL_FROM_NAME=College Database System
```

#### Step 4: Test the Configuration
1. Save the `.env` file
2. Restart the backend server:
   ```powershell
   # Stop the current server (Ctrl+C)
   # Then restart:
   cd C:\Users\manoj\Desktop\major\backend
   .venv\Scripts\activate
   python main.py
   ```
3. Go to the login page
4. Click "Forgot Password?"
5. Enter your username
6. **Check your Gmail inbox** for the OTP email

---

### Option 2: Institutional Email Server

If your college has its own email server (e.g., `mail.college.edu`), contact your IT department for:

1. **SMTP Server Address** (e.g., `smtp.college.edu`)
2. **SMTP Port** (usually 587 for TLS or 465 for SSL)
3. **Email Account Credentials** (username and password)
4. **TLS/SSL Requirements**

Then update `.env`:
```bash
MAIL_SERVER=smtp.college.edu
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=dbsystem@college.edu
MAIL_PASSWORD=your_institutional_password
MAIL_FROM=dbsystem@college.edu
MAIL_FROM_NAME=College Database System
```

---

### Option 3: Outlook/Hotmail (Alternative)

#### Step 1: Enable Two-Factor Authentication
1. Go to: https://account.microsoft.com/security
2. Enable **Two-step verification**

#### Step 2: Create App Password
1. Go to: https://account.microsoft.com/security
2. Under **Advanced security options**, find **App passwords**
3. Click **Create a new app password**
4. Copy the generated password

#### Step 3: Update `.env`
```bash
MAIL_SERVER=smtp-mail.outlook.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your_email@outlook.com
MAIL_PASSWORD=your_app_password_here
MAIL_FROM=your_email@outlook.com
MAIL_FROM_NAME=College Database System
```

---

## 🎨 Customization Options

### Change Email Branding

Edit `backend/.env`:
```bash
# Application name (appears in email subject and body)
APP_NAME=Your College Name - Student Database

# Sender display name (what recipients see in their inbox)
MAIL_FROM_NAME=Your College Name IT Department
```

### Adjust OTP Settings

Edit `backend/.env`:
```bash
# OTP validity period (default: 2 minutes)
OTP_EXPIRY_SECONDS=120

# Cooldown between OTP requests (default: 30 seconds)
OTP_RESEND_COOLDOWN_SECONDS=30

# Maximum wrong OTP attempts before lock (default: 5)
OTP_MAX_ATTEMPTS=5

# Rate limit: max OTP requests per email per hour (default: 5)
OTP_MAX_REQUESTS_PER_HOUR=5
```

---

## 🔍 Troubleshooting

### Problem: "SMTP authentication failed" Error

**Cause**: Wrong username/password or regular Gmail password instead of App Password

**Solution**:
1. Double-check you're using the 16-character App Password (not your Gmail password)
2. Remove all spaces from the App Password
3. Verify MAIL_USERNAME is the correct email address
4. Make sure 2-Step Verification is enabled

### Problem: "Network error" or Timeout

**Cause**: Firewall blocking SMTP traffic or wrong server/port

**Solution**:
1. Check if port 587 is open on your network
2. Try alternative port 465 with SSL:
   ```bash
   MAIL_PORT=465
   MAIL_USE_TLS=false  # Use SSL instead
   ```
3. Disable antivirus/firewall temporarily to test

### Problem: Emails Going to Spam

**Solution**:
1. Ask recipients to mark the email as "Not Spam"
2. Add your email to their contacts
3. For production, consider using a professional email service (SendGrid, AWS SES, etc.)

### Problem: Still Seeing Console OTP in Production

**Cause**: Empty/whitespace in MAIL_USERNAME or MAIL_PASSWORD

**Solution**:
1. Open `backend/.env`
2. Verify both fields have actual values (no spaces, no quotes)
3. Restart the server after saving

---

## 🔒 Security Best Practices

### DO:
✅ Use Gmail App Passwords (NOT your regular password)  
✅ Keep `.env` file private and never commit to Git  
✅ Use strong passwords for email accounts  
✅ Rotate credentials every 3-6 months  
✅ Monitor OTP request logs for abuse  

### DON'T:
❌ Use your personal Gmail password in production  
❌ Share SMTP credentials with unauthorized users  
❌ Commit `.env` file to version control  
❌ Disable rate limiting in production  
❌ Use public email providers for high-volume sending  

---

## 📊 Monitoring Email Delivery

### Check Server Logs

When the backend is running, you'll see logs like:
```
[EMAIL] Sending OTP email to student@example.com for user john_doe
[EMAIL] OTP email delivered successfully to student@example.com
```

### Check for Errors

If delivery fails:
```
[EMAIL] SMTP authentication failed: (535, ...)
[OTP] Email delivery failed for user_id=4: SMTP authentication failed
```

This means credentials are incorrect — follow troubleshooting steps above.

---

## 🌐 For Universal Deployment (Production Server)

### If Deploying to Cloud (AWS, Azure, GCP):

1. **Use Environment Variables** (not `.env` file):
   - Set variables in your cloud provider's console
   - Example (AWS Elastic Beanstalk): Configure environment properties
   - Example (Azure App Service): Configure application settings

2. **Use Professional Email Service** for reliability:
   - **SendGrid**: Free tier allows 100 emails/day
   - **AWS SES**: Very cheap, highly reliable
   - **Mailgun**: Good free tier for small apps

3. **Configure DNS/SPF/DKIM** (advanced):
   - Prevents emails from going to spam
   - Ask your domain administrator or cloud provider

### SendGrid Setup (Recommended for Production)

1. Sign up at: https://sendgrid.com
2. Create API key
3. Update `.env`:
   ```bash
   MAIL_SERVER=smtp.sendgrid.net
   MAIL_PORT=587
   MAIL_USE_TLS=true
   MAIL_USERNAME=apikey  # Literally the word "apikey"
   MAIL_PASSWORD=your_sendgrid_api_key_here
   MAIL_FROM=noreply@yourdomain.com
   MAIL_FROM_NAME=College Database System
   ```

---

## ✅ Quick Checklist

Before going to production:

- [ ] 2-Step Verification enabled on email account
- [ ] App Password generated and copied
- [ ] `backend/.env` updated with correct credentials
- [ ] All spaces removed from App Password
- [ ] `APP_NAME` and `MAIL_FROM_NAME` customized
- [ ] Backend server restarted after changes
- [ ] Test OTP delivery to real email address
- [ ] Verify email arrives within 10 seconds
- [ ] Check spam folder if not in inbox
- [ ] Add sender to contacts/whitelist

---

## 🆘 Need Help?

1. **Check backend console logs** for detailed error messages
2. **Verify credentials** at: https://myaccount.google.com/apppasswords
3. **Test SMTP connection** manually:
   ```python
   # Run this in Python to test SMTP:
   import smtplib
   server = smtplib.SMTP('smtp.gmail.com', 587)
   server.starttls()
   server.login('your_email@gmail.com', 'your_app_password')
   print("✅ SMTP authentication successful!")
   server.quit()
   ```

---

## 📝 Summary

**Current State**: ✅ Dev mode working (console OTP)  
**Next Action**: Follow **Option 1 (Gmail)** steps above  
**Time Required**: ~10 minutes  
**Result**: Real email delivery to all users  

**After Setup**: Restart backend → Test forgot password → Check email inbox!
