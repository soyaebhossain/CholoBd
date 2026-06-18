# Cholo Bd
## Security & Policy Framework

This document defines the production security architecture, moderation controls, privacy structure, and operating policies for `Cholo Bd`, a travel social platform that includes user accounts, trip logging, albums, stories, travel history notes, saved spots, media uploads, community discussion, public profiles, and analytics dashboards.

The framework is written for a Django-based deployment and assumes a public internet-facing platform with authenticated members, moderators, and administrators.

## 1. Platform Overview

### 1.1 Business and Security Context

Cholo Bd stores a mix of personal identity data, user-generated content, media uploads, travel locations, and behavioral analytics. That makes it both a social platform and a travel record system. The platform must protect:

- Authentication credentials and session tokens
- Personally identifiable information such as name, email, phone, and profile metadata
- Sensitive travel history that may reveal movement patterns, home region, trip timing, and routines
- User-generated content including posts, comments, stories, notes, and media
- Public-facing community features that are targets for spam, abuse, harassment, malware, and impersonation
- Administrative interfaces that can alter content, access user data, and enforce platform policy

### 1.2 Main Security Requirements

- Confidentiality: private travel records, drafts, phone numbers, and non-public profiles must not leak.
- Integrity: users must not alter other users' trips, albums, posts, or profile settings.
- Availability: the platform should resist spam floods, brute force attempts, abusive uploads, and denial-of-service patterns.
- Accountability: moderation and admin actions must be auditable.
- Safety: harmful or illegal content must be removable quickly.
- Privacy by default: public exposure should be explicit, not assumed.

### 1.3 Main Risks

- Account takeover through weak passwords, credential stuffing, brute force, or reused sessions
- Insecure direct object reference allowing one user to edit another user's trip or media
- Malware or oversized media uploads causing storage abuse or malicious file delivery
- Stored XSS through unsafe rendering of stories, comments, captions, or profile text
- Privacy leakage through public profiles, exposed travel dates, location patterns, and album visibility
- Spam, scams, harassment, unsafe travel advice, and community abuse
- Admin compromise due to poor credential hygiene or exposed admin URLs
- Secret leakage from hardcoded keys or misconfigured production settings
- Data loss or ransomware without tested backups and restore procedures

## 2. Authentication Security

### 2.1 Login System Design

- Use Django's built-in authentication framework as the base.
- Require unique usernames and verified email addresses.
- Enforce email verification before enabling community posting, public profile publishing, or recovery-sensitive actions.
- Protect logins with CSRF, HTTPS-only cookies, rate limiting, and account lockout thresholds.

### 2.2 Strong Password Policy

Recommended password policy:

- Minimum length: 12 characters for standard users
- Minimum length: 16 characters for admin and moderator accounts
- Reject common passwords using Django's `CommonPasswordValidator`
- Reject passwords similar to username, email, or full name
- Encourage passphrases instead of short complex strings
- Deny breached passwords through a have-I-been-pwned style offline or API-backed check when possible

Recommended Django validators:

- `UserAttributeSimilarityValidator`
- `MinimumLengthValidator(min_length=12)`
- `CommonPasswordValidator`
- `NumericPasswordValidator`

### 2.3 Email Verification

- Send a signed, time-limited verification token on signup
- Require verification before:
  - posting in community
  - publishing public stories
  - making profile public
  - requesting sensitive account recovery
- Expire tokens within 24 hours
- Log email verification events

### 2.4 Password Hashing

- Use Django's default password hashing with `PBKDF2PasswordHasher`
- Prefer `Argon2PasswordHasher` in production if operationally available
- Never store or log plaintext passwords
- Re-hash passwords automatically when hasher settings upgrade

Recommended order:

```python
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]
```

### 2.5 Session Protection

- Use HTTPS-only session cookies
- Set `HttpOnly` on session cookies
- Use `SameSite=Lax` or `SameSite=Strict` where practical
- Rotate session on login and password change
- Expire idle sessions after a defined inactivity window
- Invalidate all active sessions on password reset or suspected compromise
- Store session backend server-side, not in signed client cookies for privileged accounts

### 2.6 Account Lockout and Brute Force Protection

- Lock account after 5 to 10 failed login attempts from the same account within 15 minutes
- Add IP-based and username-based throttles
- Introduce exponential backoff for repeated failures
- Show generic error messages to prevent account enumeration
- Alert user by email after suspicious failed login bursts

Recommended protections:

- `django-axes` or equivalent
- Reverse-proxy rate limiting at Nginx or Cloudflare
- Audit events for failed and successful logins

### 2.7 Optional Two-Factor Authentication

Recommended for:

- Moderators
- Admins
- Any user who enables it voluntarily

Preferred methods:

- TOTP authenticator apps
- Backup recovery codes
- Avoid SMS as the only factor

### 2.8 Django Best Practices

- Use Django auth, permissions, CSRF, signed cookies, and password reset flows
- Never write custom password hashing logic
- Do not expose raw login exception details
- Protect all auth endpoints behind HTTPS
- Separate staff login monitoring from normal user login analytics

## 3. Authorization Model

### 3.1 Roles

#### Guest

- Can browse public landing pages
- Can view only public destinations, public community content, and public profiles
- Cannot create or edit any object
- Cannot access member dashboards or personal travel records

#### Member

- Can manage own profile, trips, albums, stories, travel history, saved spots, posts, and comments
- Can set privacy controls on supported content
- Can report content and block users
- Cannot moderate others or access admin tools

#### Moderator

- Can review reports
- Can hide posts/comments pending review
- Can remove content that violates policy
- Can suspend or restrict community participation
- Cannot access billing secrets, infrastructure secrets, or raw password data

#### Admin

- Full platform administration
- Can manage moderators, site-wide policy, configuration, abuse response, and incident handling
- Can access audit trails
- Must use MFA and IP-restricted admin access

### 3.2 Object-Level Permissions

Core rule: ownership is required for mutation of user-created content.

Members can only edit or delete their own:

- Trips
- Albums
- Album items
- Stories
- Travel history notes
- Saved spots
- Community posts
- Community comments
- Profile settings

Moderators may hide or remove content but should not silently rewrite user content without an audit event.

### 3.3 Enforcement Pattern in Django

- Filter querysets by `user=request.user` for owned resources
- Re-check ownership in detail/update/delete views
- Use object-level checks before every mutation
- For APIs, never trust object IDs from the client without access checks

Recommended service pattern:

```python
def can_edit_trip(user, trip):
    return user.is_authenticated and (trip.user_id == user.id or user.is_staff)
```

## 4. Media Upload Security

The platform supports images, videos, and audio. Uploads are a high-risk area because they can carry malware, oversized payloads, dangerous file types, or content that abuses storage and moderation capacity.

### 4.1 Allowed File Types

Recommended allowlist:

- Images: `jpg`, `jpeg`, `png`, `webp`, `gif`
- Audio: `mp3`, `wav`, `ogg`, `m4a`
- Video: `mp4`, `webm`, `mov`

Do not allow:

- `svg` for user uploads unless sanitized server-side
- Executables, scripts, HTML, XML, archives, office macros, or arbitrary binary files

### 4.2 File Size Limits

Recommended limits:

- Avatar: 2 MB
- Standard image: 5 MB
- Audio: 10 MB
- Video: 50 MB

Apply limits in:

- Reverse proxy
- Django request size limits
- Form or serializer validation
- Background processing workers

### 4.3 Filename Sanitization

- Strip path components
- Normalize to safe ASCII or storage-safe filenames
- Limit length
- Replace dangerous characters
- Never trust the original filename for display or storage paths

### 4.4 Virus and Malware Scanning

- Scan uploads asynchronously before publishing them
- Use ClamAV or an equivalent antivirus service
- Mark uploaded files as `pending_scan`, `clean`, or `quarantined`
- Do not serve files until scan passes
- Quarantine suspicious files and alert moderators/admins

### 4.5 Storage Isolation

- Store media outside the application code directory
- Serve user uploads from object storage or a dedicated media domain
- Do not allow uploaded files to execute as server-side code
- Use separate storage buckets or prefixes by media class and environment
- Apply private ACLs by default, then publish through signed or controlled URLs if needed

### 4.6 Media Validation

Validate:

- extension allowlist
- size limit
- content type consistency
- image open/decode success
- safe re-encoding for images where possible
- duration and codec policies for video and audio

### 4.7 Safe Image Processing

- Re-encode uploaded images to a safe output format where possible
- Strip EXIF metadata unless explicitly needed
- Remove GPS metadata from photos by default
- Generate thumbnails in background jobs
- Use library-level protections against decompression bombs

### 4.8 Best Practices

- Use background workers for transcoding and scanning
- Rate-limit uploads per account and per IP
- Keep a moderation path for flagged media
- Audit upload, replace, delete, and moderator takedown actions

## 5. Community Safety System

### 5.1 Safety Controls

- Post and comment reporting with categorized reasons
- User blocking and mute controls
- Spam detection and rate limiting
- Moderator review queues
- Fast takedown for illegal, violent, exploitative, or doxxing content
- Repeat offender escalation

### 5.2 Reporting Workflow

Required report reasons:

- Spam or scam
- Harassment or hate
- Sexual or explicit content
- Violence or threats
- Dangerous travel misinformation
- Copyright violation
- Privacy violation or doxxing
- Self-harm or crisis concern
- Other

Workflow:

1. User reports content
2. System stores report and risk score
3. High-risk categories auto-hide or escalate
4. Moderator reviews evidence
5. Action is logged with actor, timestamp, reason, and affected object

### 5.3 Spam Protection

- Rate-limit posting, commenting, and media uploads
- Detect repeated links, repeated hashtags, repeated identical comments
- Use CAPTCHA or challenge for suspicious activity
- Apply trust scores for new accounts
- Delay or queue first-time public posts for review if risk is high

### 5.4 Content Removal

- Support soft-hide for investigation
- Support hard-delete for illegal material
- Preserve evidence for abuse cases and lawful requests
- Notify user when moderation action is taken unless safety policy forbids it

### 5.5 Community Rules

- Respect other travelers
- No harassment, hate, threats, or stalking
- No unsafe or intentionally misleading travel advice
- No pornographic, exploitative, or violent content
- No doxxing or sharing private contact or location data without consent
- No spam, fake promotions, or fraud
- No copyright infringement

## 6. Privacy Policy Structure

### 6.1 Data Collected

Identity and account data:

- Name
- Username
- Email
- Phone number
- Password hash

Profile and social data:

- Avatar
- Bio
- Public/private visibility settings
- Community participation settings

Travel content:

- Trips
- Travel dates
- Divisions, districts, upazilas, and spots
- Travel history notes
- Stories
- Albums and captions
- Saved spots

Community data:

- Posts
- Comments
- Reactions
- Reports
- Moderation decisions

Technical and security data:

- IP addresses
- device or browser metadata
- session identifiers
- login timestamps
- abuse prevention logs

### 6.2 How Data Is Used

- To create and secure user accounts
- To display profiles and social content according to privacy settings
- To power dashboards, travel history, and saved locations
- To moderate abuse and protect users
- To troubleshoot, audit, and secure the service
- To send account notices, security alerts, and optional community updates

### 6.3 Privacy Settings Model

Recommended settings:

- Public profile on or off
- Show full name or username only
- Allow community mentions
- Allow direct messages
- Receive community notifications
- Story visibility: private, followers-only, public
- Album visibility: private, share-link, public
- Trip visibility: private by default

### 6.4 Public vs Private Defaults

- Trips: private by default
- Travel history notes: private by default
- Saved spots: private by default
- Profile: private by default until explicitly made public
- Stories: explicit visibility selection required
- Albums: explicit visibility selection required

### 6.5 Policy Sections to Include

- What data is collected
- Why it is collected
- Legal basis or consent basis, depending on jurisdiction
- How long it is retained
- Who it is shared with
- When it is published publicly
- How users can delete or export their data
- How users can contact the platform for privacy requests

## 7. Terms of Service

### 7.1 Allowed Content

- Personal travel experiences
- Trip planning questions
- Budget discussions
- Hotel and transport advice
- Travel photos and lawful media
- Informational community participation

### 7.2 Prohibited Content

- Illegal content
- Harassment, hate, threats, and stalking
- Fraud, scams, phishing, or impersonation
- Malware distribution
- Pornographic or exploitative material
- Copyright infringement
- Doxxing or publishing private information without consent
- Dangerous misinformation that may cause harm

### 7.3 Copyright Policy

- Users must upload only content they own or are licensed to share
- Platform may remove infringing content on notice
- Repeat infringers may lose account access
- Provide a notice-and-takedown workflow

### 7.4 User Responsibility

- Users are responsible for their account security
- Users are responsible for legality and accuracy of content they post
- Users must not misuse the platform for scraping, spam, or abuse

### 7.5 Community Behavior Rules

- Be respectful
- Give travel advice in good faith
- Do not pressure others to reveal personal details
- Do not use the platform to target or track people

## 8. Django Security Configuration

### 8.1 Recommended Production Settings

```python
DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
```

### 8.2 Setting Explanations

- `DEBUG`: must be `False` in production to prevent stack trace leakage and sensitive settings exposure.
- `SECURE_SSL_REDIRECT`: forces HTTPS for all requests.
- `CSRF_COOKIE_SECURE`: prevents CSRF cookie transmission over plaintext HTTP.
- `SESSION_COOKIE_SECURE`: prevents session cookie transmission over plaintext HTTP.
- `SECURE_HSTS_SECONDS`: instructs browsers to remember HTTPS-only policy.
- `X_FRAME_OPTIONS`: mitigates clickjacking by disallowing framing.
- `SECURE_CONTENT_TYPE_NOSNIFF`: prevents MIME sniffing attacks.

Additional recommendations:

- `CSRF_TRUSTED_ORIGINS` for reverse proxy or known frontend domains
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
- `ALLOWED_HOSTS` restricted to real domains only

## 9. Database Security

### 9.1 Secure Database Architecture

- Use a managed database or isolated database host
- Restrict database access by network policy and firewall
- Use unique database credentials per environment
- Rotate secrets through environment variables or secret managers
- Never commit credentials to source control

### 9.2 Passwords and Secrets

- Store application secrets in environment variables or a secret manager
- Hash passwords using Django hashers only
- Encrypt backups at rest
- Encrypt database connections in transit

### 9.3 Foreign Key Protection

- Use foreign keys and referential integrity to prevent orphaned records
- Prefer `PROTECT` or soft delete for critical linked data where accidental deletion is risky
- For user-owned content, use application-layer ownership checks and explicit delete flows

### 9.4 Audit Logs

Audit the following:

- Login success and failure
- Password reset requests
- Email verification
- Content creation, update, delete
- Moderator actions
- Admin access
- Privacy setting changes
- Data export and deletion requests

### 9.5 Backups

- Daily encrypted backups minimum
- Point-in-time recovery if supported
- Separate backup account and storage location
- Test restore procedures at least monthly

### 9.6 Soft Delete

Recommended for:

- community posts
- comments
- stories
- reports
- moderation actions

Benefits:

- incident investigation
- moderator reversibility
- user appeal handling
- accidental deletion recovery

## 10. Deployment Security

### 10.1 Server and Network Security

- Terminate HTTPS at a hardened reverse proxy
- Use TLS 1.2+ only
- Redirect all HTTP to HTTPS
- Restrict admin endpoints by IP or VPN
- Disable unused ports and services
- Run application workers with least privilege

### 10.2 Reverse Proxy Best Practices

- Nginx or Caddy in front of Django
- request size limits
- rate limiting
- security headers
- logging and access control
- media caching and isolation

### 10.3 Secrets Management

- Use `.env` only for local development
- Use a proper secret store in production
- Rotate secret keys, API tokens, and database passwords
- Never expose secrets in logs, exception emails, or process listings

### 10.4 Admin Access Protection

- Separate admin accounts from normal user accounts
- Require MFA
- Limit by IP allowlist or VPN
- Log all admin actions
- Alert on new staff login from unknown device or IP

### 10.5 Host Maintenance

- Apply OS and package updates regularly
- Remove unused packages and services
- Use centralized log collection
- Monitor disk usage, upload growth, background jobs, and abuse spikes

## 11. Community Moderation Tools

Moderators need dedicated tools beyond the public interface.

### 11.1 Required Moderation Features

- Review queue for reported posts, comments, stories, and media
- One-click hide, remove, restore, warn, suspend, and ban actions
- User risk history and prior moderation actions
- Evidence snapshots for abusive content
- Search by username, post ID, report reason, district, or date

### 11.2 Moderation Dashboard

Recommended widgets:

- open reports
- urgent reports
- recent bans
- content hidden today
- top repeat offenders
- pending media scan failures
- unresolved privacy complaints

### 11.3 Content Actions

- Hide post
- Hide comment
- Remove post permanently
- Remove media only
- Freeze thread
- Lock account from community participation
- Full account suspension for severe abuse

### 11.4 Governance Controls

- Every moderator action must store actor, reason, object, and timestamp
- High-impact actions should require reason codes
- Appeals workflow should exist for users
- Admins should review moderator activity periodically

## 12. Production Security Checklist

### Application

- `DEBUG=False`
- real `SECRET_KEY` from environment
- restricted `ALLOWED_HOSTS`
- CSRF enabled on all forms and state-changing endpoints
- session and CSRF cookies marked secure
- HTTPS enforced
- upload size limits configured
- upload extension allowlist enforced
- profile privacy settings enforced
- object-level ownership checks in every edit/delete path

### Authentication

- email verification enabled
- strong password validators enabled
- brute-force protection enabled
- optional MFA enabled for users, mandatory for staff
- session rotation on login and password change

### Community Safety

- report flow live
- moderator dashboard live
- spam throttles active
- block and mute system active
- abuse logging active

### Infrastructure

- reverse proxy configured
- HSTS enabled
- backups encrypted and tested
- logs centralized
- admin access IP-restricted
- OS and dependencies patched

### Data Governance

- privacy policy published
- terms of service published
- retention schedule defined
- data deletion workflow defined
- export workflow defined
- incident response contacts documented

## Immediate Practical Recommendations for This Project

For the current Django codebase, the first production-focused priorities should be:

1. Move secrets and security toggles to environment variables and disable debug in production.
2. Enforce upload validation, quarantine, and scanning before serving user media.
3. Apply privacy controls consistently to public profile previews, community notifications, and future story or album visibility controls.
4. Add rate limiting and account lockout to login, post, comment, and upload flows.
5. Build moderation models for reports, bans, hidden content states, and audit logs before scaling community features.
