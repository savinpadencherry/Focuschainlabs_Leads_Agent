# Flutter mobile integration

Copy these files into [Focuschainlabs_mobile](https://github.com/savinpadencherry/Focuschainlabs_mobile):

| This repo | Mobile repo |
|-----------|-------------|
| `integrations/flutter/lib/features/leads/view/leads_page.dart` | `lib/features/leads/view/leads_page.dart` |
| `integrations/flutter/lib/core/services/crm/leads_crm_service.dart` | `lib/core/services/crm/leads_crm_service.dart` |
| `integrations/flutter/lib/core/services/crm/supabase_crm_service.dart` | `lib/core/services/crm/supabase_crm_service.dart` |

## Also update in the mobile repo

Add `updateStatus` to `GithubCrmService` and `MockLeadsCrmService`:

```dart
@override
Future<bool> updateStatus(String contactId, String newStatus) async {
  // Github: load contacts.json, patch status, commit via Contents API
  // Mock: return true
}
```

## What you get

- Search bar on Leads tab (filters client-side — no endless scroll)
- Status button on each card + bottom sheet to advance or pick stage
- Multi-select mode (checklist icon) + bulk stage advance
- Writes go to Supabase `contacts.status` — same field the CRM web app uses

Full architecture and WhatsApp checklist: `docs/LEADS_SEARCH_BROADCAST.md`
