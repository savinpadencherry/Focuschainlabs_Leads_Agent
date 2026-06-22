import 'package:supabase_flutter/supabase_flutter.dart';

import '../../config/app_config.dart';
import '../../models/crm.dart';
import '../../models/enums.dart';
import '../../models/extraction.dart';
import 'leads_crm_service.dart';

/// CRM backed by Supabase (Postgres). Reads/writes the `contacts` and
/// `interactions` tables that the Leads Agent data was migrated into, so the
/// mobile app and the website share one database.
class SupabaseCrmService implements LeadsCrmService {
  SupabaseClient get _db => Supabase.instance.client;

  @override
  Future<List<CrmContact>> listLeads() async {
    try {
      final List<dynamic> rows = await _db
          .from('contacts')
          .select()
          .order('updated_at', ascending: false)
          .limit(500);
      return rows
          .map((dynamic r) => CrmContact.fromJson(Map<String, dynamic>.from(r as Map)))
          .toList();
    } catch (_) {
      return <CrmContact>[];
    }
  }

  @override
  Future<bool> updateStatus(String contactId, String newStatus) async {
    try {
      final String now = DateTime.now().toUtc().toIso8601String();
      final Map<String, dynamic> patch = <String, dynamic>{
        'status': newStatus,
        'updated_at': now,
      };
      if (newStatus == 'won' || newStatus == 'lost') {
        patch['deal_status'] = newStatus;
      }
      await _db.from('contacts').update(patch).eq('id', contactId);
      return true;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<List<CrmInteraction>> history(String contactRef) async {
    try {
      final String contactId = await _resolveId(contactRef) ?? contactRef;
      final List<dynamic> rows = await _db
          .from('interactions')
          .select()
          .eq('contact_id', contactId)
          .order('created_at', ascending: false)
          .limit(50);
      return rows
          .map((dynamic r) =>
              CrmInteraction.fromJson(Map<String, dynamic>.from(r as Map)))
          .toList();
    } catch (_) {
      return <CrmInteraction>[];
    }
  }

  @override
  Future<CrmWriteResult> upsertLead(
    Extraction extraction, {
    String? transcript,
  }) async {
    try {
      final String now = DateTime.now().toUtc().toIso8601String();
      final String? followUp =
          extraction.followUpDate?.toIso8601String().split('T').first;

      final Map<String, dynamic>? existing = await _db
          .from('contacts')
          .select('id,name')
          .eq('name', extraction.client)
          .maybeSingle();

      String id;
      String action;
      if (existing != null) {
        id = existing['id'].toString();
        action = 'merged';
        await _db.from('contacts').update(<String, dynamic>{
          if (extraction.dealStageChange != null) 'status': extraction.dealStageChange,
          'sentiment': extraction.sentiment.wire,
          if (followUp != null) 'next_follow_up': followUp,
          'updated_at': now,
        }).eq('id', id);
      } else {
        action = 'created';
        final Map<String, dynamic> inserted = await _db
            .from('contacts')
            .insert(<String, dynamic>{
              'name': extraction.client,
              'company': extraction.client,
              'status': extraction.dealStageChange ?? 'new',
              'deal_status': 'open',
              'source': 'mobile',
              'sentiment': extraction.sentiment.wire,
              if (followUp != null) 'next_follow_up': followUp,
              'tags': <String>['mobile'],
            })
            .select('id')
            .single();
        id = inserted['id'].toString();
      }

      await _db.from('interactions').insert(<String, dynamic>{
        'contact_id': id,
        'author': 'Mr. Rex (mobile)',
        'kind': 'comment',
        'body': (transcript == null || transcript.isEmpty)
            ? extraction.summary
            : '${extraction.summary}\n\n“$transcript”',
      });

      return CrmWriteResult(
        ok: true,
        contactId: id,
        contactName: extraction.client,
        action: action,
        webUrl: AppConfig.hasCrmWeb ? AppConfig.crmWebUrl : null,
      );
    } catch (e) {
      return CrmWriteResult.failure(e.toString());
    }
  }

  Future<String?> _resolveId(String ref) async {
    try {
      final Map<String, dynamic>? byName = await _db
          .from('contacts')
          .select('id')
          .or('id.eq.$ref,name.eq.$ref')
          .maybeSingle();
      return byName?['id']?.toString();
    } catch (_) {
      return null;
    }
  }
}
