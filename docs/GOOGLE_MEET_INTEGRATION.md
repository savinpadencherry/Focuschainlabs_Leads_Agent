# Google Meet Integration Guide

## Architecture Overview

```
CRM Contact → Schedule Meeting → Generate Meet Link → Store in CRM
                                        ↓
                                  Send Notifications
                                        ↓
                                  Meeting Happens
                                        ↓
                                  Log Notes & Actions
```

## How It Works

1. **Meeting Scheduling:**
   - Sales rep opens contact in CRM
   - Clicks "Schedule Meeting" button
   - Selects date/time and adds agenda
   - System generates Google Meet link
   - Link stored in contact's comment thread
   - Optional: Email/WhatsApp notification sent

2. **Meeting Execution:**
   - Both parties join via Meet link
   - Meeting happens (video/audio)
   - Rep takes notes during call

3. **Post-Meeting:**
   - Rep adds meeting notes in CRM
   - AI summarizes key points and action items
   - Contact status updated (e.g., "Qualified" → "Proposal")
   - Follow-up tasks created automatically

4. **Calendar Integration (Optional):**
   - Sync with Google Calendar
   - Team can see all scheduled meetings
   - Automatic reminders

## Setup Instructions

### Option 1: Simple Meet Links (No API Required)

**Pros:**
- No Google Cloud setup needed
- Works immediately
- Free forever
- Perfect for Streamlit Cloud Community

**Cons:**
- Random meeting codes (not calendar events)
- No automatic calendar sync
- Manual notification sending

**Implementation:**
Already built into CRM! Just use it:

1. Open contact in CRM
2. Click "Add Comment" → "Schedule Meeting"
3. System generates: `https://meet.google.com/abc-defg-hij`
4. Link saved to contact thread
5. Copy link and send to contact via email/WhatsApp

### Option 2: Google Calendar API (Advanced)

**Pros:**
- Creates calendar events
- Automatic invites sent
- Calendar sync
- Reminders built-in

**Cons:**
- Requires Google Cloud project
- OAuth setup needed
- More complex configuration

**Setup Steps:**

1. **Create Google Cloud Project:**
   ```
   - Go to https://console.cloud.google.com
   - Create new project: "CRM Calendar Integration"
   - Enable Google Calendar API
   - Enable Google Meet API (if available)
   ```

2. **Create Service Account:**
   ```
   - IAM & Admin → Service Accounts
   - Create service account: "crm-calendar-bot"
   - Grant role: "Calendar Editor"
   - Create JSON key → Download
   ```

3. **Share Calendar:**
   ```
   - Open Google Calendar
   - Settings → Share with specific people
   - Add service account email
   - Permission: "Make changes to events"
   ```

4. **Configure Streamlit Secrets:**
   ```toml
   [google_calendar]
   type = "service_account"
   project_id = "your-project-id"
   private_key_id = "your-key-id"
   private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
   client_email = "crm-calendar-bot@your-project.iam.gserviceaccount.com"
   client_id = "123456789"
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   
   GOOGLE_CALENDAR_ID = "your-calendar-id@group.calendar.google.com"
   ```

5. **Install Dependencies:**
   ```bash
   pip install google-auth google-auth-oauthlib google-api-python-client
   ```

## Usage

### Scheduling a Meeting (Simple)

1. **In CRM:**
   - Open contact detail page
   - Click "Schedule Meeting" button
   - Fill in details:
     - Date & Time
     - Duration (30/60/90 min)
     - Agenda/Topic
   - Click "Generate Meet Link"

2. **System Actions:**
   - Creates unique Meet link
   - Adds comment to contact thread:
     ```
     📅 Meeting Scheduled
     Date: 2024-06-15 at 3:00 PM IST
     Duration: 60 minutes
     Link: https://meet.google.com/abc-defg-hij
     Agenda: Discuss Q3 proposal and pricing
     ```

3. **Send Invitation:**
   - Copy Meet link
   - Send via email or WhatsApp:
     ```
     Hi [Name],
     
     Looking forward to our meeting on June 15 at 3:00 PM IST.
     
     Join here: https://meet.google.com/abc-defg-hij
     
     Agenda: Discuss Q3 proposal and pricing
     
     Best regards,
     [Your Name]
     ```

### During Meeting

1. **Join Meeting:**
   - Click Meet link from CRM
   - Opens in browser
   - Start video call

2. **Take Notes:**
   - Keep CRM open in another tab
   - Jot down key points in notes field
   - Mark important action items

### After Meeting

1. **Log Meeting Notes:**
   - In CRM, add new comment
   - Type: "Meeting Notes"
   - Content:
     ```
     ✅ Meeting completed
     
     Key Discussion Points:
     - Budget confirmed: ₹50L
     - Timeline: Start in Q3
     - Decision makers: CEO + CFO
     
     Action Items:
     - [ ] Send proposal by June 20
     - [ ] Schedule demo for June 25
     - [ ] Follow up on pricing questions
     
     Next Steps:
     Proposal review meeting on June 30
     ```

2. **Update Contact Status:**
   - Change status: "Contacted" → "Qualified"
   - Update deal value if discussed
   - Set follow-up date

3. **AI Summary (Optional):**
   - Click "Summarize with AI"
   - AI extracts:
     - Key decisions
     - Action items
     - Next steps
     - Sentiment analysis

## Features

### Current Features (Built-in)

✅ **Meet Link Generation**
- Random unique codes
- Instant creation
- No API limits

✅ **CRM Integration**
- Links stored in contact thread
- Searchable by date/contact
- Full conversation history

✅ **Manual Notifications**
- Copy link to clipboard
- Send via email/WhatsApp
- Template messages available

### Enhanced Features (With Calendar API)

🚀 **Automatic Calendar Events**
- Creates Google Calendar event
- Sends email invites automatically
- Adds Meet link to event

🚀 **Reminders**
- Email reminder 1 day before
- Email reminder 1 hour before
- Optional WhatsApp reminders

🚀 **Team Calendar View**
- See all scheduled meetings
- Avoid double-booking
- Team availability

🚀 **Meeting Analytics**
- Meetings per contact
- Average meeting duration
- Conversion rate (meeting → deal)

## Best Practices

### Before Meeting

1. **Prepare Agenda:**
   - Clear objectives
   - Questions to ask
   - Materials to share

2. **Send Reminder:**
   - 1 day before: Confirm attendance
   - 1 hour before: Send link again
   - Include agenda in reminder

3. **Test Technology:**
   - Check camera/mic
   - Ensure stable internet
   - Have backup phone number

### During Meeting

1. **Start on Time:**
   - Join 2 minutes early
   - Wait max 5 minutes for no-show

2. **Take Notes:**
   - Key points
   - Action items
   - Next steps

3. **Confirm Next Steps:**
   - Summarize at end
   - Agree on follow-up date
   - Clarify action items

### After Meeting

1. **Log Immediately:**
   - Notes while fresh
   - Update CRM status
   - Set follow-up tasks

2. **Send Summary:**
   - Email recap within 24 hours
   - List action items
   - Confirm next meeting

3. **Follow Up:**
   - Complete action items
   - Check in before next meeting
   - Keep momentum going

## Troubleshooting

### Meet Link Not Working

**Issue:** Link shows "Meeting not found"

**Solutions:**
- Meet links expire after ~90 days of inactivity
- Generate new link if old
- Ensure no typos in link

### Cannot Join Meeting

**Issue:** "You need permission to join"

**Solutions:**
- Meeting host must join first
- Check if meeting is scheduled for future
- Verify link is correct

### Calendar API Errors

**Issue:** "Insufficient permissions"

**Solutions:**
- Verify service account has Calendar Editor role
- Check calendar is shared with service account
- Ensure API is enabled in Google Cloud

**Issue:** "Invalid credentials"

**Solutions:**
- Re-download service account JSON
- Check private key format (must include \n)
- Verify project ID matches

## Integration with WhatsApp

**Send Meeting Link via WhatsApp:**

1. Schedule meeting in CRM
2. Copy Meet link
3. Open contact's WhatsApp thread
4. Send message:
   ```
   Hi [Name]! 👋
   
   Our meeting is confirmed for [Date] at [Time].
   
   Join here: [Meet Link]
   
   Looking forward to it!
   ```

**Automated Reminders:**

Set up reminder workflow:
- 1 day before: WhatsApp reminder
- 1 hour before: WhatsApp reminder with link
- Post-meeting: Thank you message

## Metrics & Analytics

Track meeting effectiveness:

- **Meetings Scheduled:** Count per week/month
- **Attendance Rate:** % of scheduled meetings that happen
- **Conversion Rate:** % of meetings → deals
- **Average Duration:** Typical meeting length
- **Follow-up Rate:** % with next meeting scheduled

## Production Checklist

- [ ] Test Meet link generation
- [ ] Verify links work in browser
- [ ] Test mobile access (iOS/Android)
- [ ] Set up notification templates
- [ ] Train team on meeting workflow
- [ ] Create meeting agenda templates
- [ ] Set up post-meeting note templates
- [ ] Configure AI summary (if using)
- [ ] Test calendar integration (if using)
- [ ] Set up meeting analytics dashboard

## Cost Breakdown

| Feature | Cost |
|---------|------|
| Google Meet (Basic) | Free |
| Google Meet (Workspace) | $6-18/user/month |
| Google Calendar API | Free |
| Google Cloud Project | Free (within limits) |

**Recommended:** Start with free basic Meet links, upgrade to Workspace if needed for recording/larger meetings.

## Support

- Google Meet Help: https://support.google.com/meet
- Calendar API Docs: https://developers.google.com/calendar
- Workspace Admin: https://admin.google.com