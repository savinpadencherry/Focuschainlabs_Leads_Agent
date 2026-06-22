import '../../models/crm.dart';
import '../../models/extraction.dart';

/// Contract for talking to the Leads Agent CRM. The GitHub implementation
/// reads/writes the repo's `data/crm/contacts.json` directly (the "database in
/// the repo"); a mock backs demo mode.
abstract interface class LeadsCrmService {
  /// Upsert a lead and append the spoken update as an interaction (F2/F5).
  Future<CrmWriteResult> upsertLead(Extraction extraction, {String? transcript});

  /// A contact's interaction history for the "show the history" view.
  Future<List<CrmInteraction>> history(String contactRef);

  /// All leads/contacts, for the in-app Leads list (pulled from the repo).
  Future<List<CrmContact>> listLeads();

  /// Update pipeline stage for a contact (search → quick status from Leads tab).
  Future<bool> updateStatus(String contactId, String newStatus);
}
