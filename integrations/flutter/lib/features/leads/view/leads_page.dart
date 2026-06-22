import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

import '../../../core/config/app_config.dart';
import '../../../core/get.dart';
import '../../../core/models/crm.dart';
import '../../../core/services/crm/leads_crm_service.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/utils/responsive.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/mono_label.dart';
import '../../../shared/widgets/state_views.dart';
import '../../../shared/widgets/web_view_screen.dart';
import '../../prep/view/prep_view.dart';

/// Pipeline order — mirrors `utils/crm_models.py` CRM_STATUSES.
const List<String> kPipelineStages = <String>[
  'new',
  'contacted',
  'qualified',
  'proposal',
  'won',
  'lost',
];

String _stageLabel(String slug) {
  switch (slug) {
    case 'new':
      return 'New';
    case 'contacted':
      return 'Contacted';
    case 'qualified':
      return 'Qualified';
    case 'proposal':
      return 'Proposal';
    case 'won':
      return 'Won';
    case 'lost':
      return 'Lost';
    default:
      return slug.isEmpty ? 'New' : slug[0].toUpperCase() + slug.substring(1);
  }
}

String? _nextStage(String current) {
  final int idx = kPipelineStages.indexOf(current);
  if (idx < 0 || idx >= kPipelineStages.length - 2) return null;
  return kPipelineStages[idx + 1];
}

bool _matchesQuery(CrmContact c, String query) {
  final String needle = query.trim().toLowerCase();
  if (needle.isEmpty) return true;
  final String blob = <String>[
    c.name,
    c.company,
    c.status,
    c.owner,
    c.value,
  ].join(' ').toLowerCase();
  return needle.split(RegExp(r'\s+')).every(blob.contains);
}

/// The in-app Leads list with search + quick status updates (shared Supabase CRM).
class LeadsPage extends StatefulWidget {
  const LeadsPage({super.key});

  @override
  State<LeadsPage> createState() => _LeadsPageState();
}

class _LeadsPageState extends State<LeadsPage> {
  late Future<List<CrmContact>> _future = app<LeadsCrmService>().listLeads();
  final TextEditingController _searchCtrl = TextEditingController();
  bool _selectMode = false;
  final Set<String> _selected = <String>{};
  List<CrmContact> _allLeads = <CrmContact>[];

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  void _refresh() => setState(() {
        _future = app<LeadsCrmService>().listLeads();
      });

  Future<void> _advanceStatus(CrmContact contact, String newStatus) async {
    final LeadsCrmService crm = app<LeadsCrmService>();
    final bool ok = await crm.updateStatus(contact.id, newStatus);
    if (!mounted) return;
    if (ok) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${contact.name} → ${_stageLabel(newStatus)}')),
      );
      _refresh();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not update status')),
      );
    }
  }

  Future<void> _bulkAdvance() async {
    final LeadsCrmService crm = app<LeadsCrmService>();
    int updated = 0;
    for (final String id in _selected) {
      CrmContact? c;
      for (final CrmContact lead in _allLeads) {
        if (lead.id == id) {
          c = lead;
          break;
        }
      }
      if (c == null) continue;
      final String? nxt = _nextStage(c.status.isEmpty ? 'new' : c.status);
      if (nxt != null && await crm.updateStatus(id, nxt)) updated++;
    }
    if (!mounted) return;
    setState(() {
      _selectMode = false;
      _selected.clear();
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Advanced $updated lead(s)')),
    );
    _refresh();
  }

  void _showStatusSheet(CrmContact contact) {
    final String cur = contact.status.isEmpty ? 'new' : contact.status;
    final String? nxt = _nextStage(cur);
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (BuildContext ctx) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Text(
                  contact.name,
                  style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17),
                ),
                Text(
                  'Current: ${_stageLabel(cur)}',
                  style: const TextStyle(color: AppColors.inkSoft),
                ),
                AppSpacing.vGapMd,
                if (nxt != null)
                  FilledButton(
                    onPressed: () {
                      Navigator.pop(ctx);
                      _advanceStatus(contact, nxt);
                    },
                    child: Text('Advance to ${_stageLabel(nxt)}'),
                  ),
                AppSpacing.vGapSm,
                DropdownButtonFormField<String>(
                  value: cur,
                  decoration: const InputDecoration(labelText: 'Set stage'),
                  items: kPipelineStages
                      .map((String s) => DropdownMenuItem<String>(
                            value: s,
                            child: Text(_stageLabel(s)),
                          ))
                      .toList(),
                  onChanged: (String? v) {
                    if (v != null) {
                      Navigator.pop(ctx);
                      _advanceStatus(contact, v);
                    }
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Leads'),
        actions: <Widget>[
          IconButton(
            tooltip: _selectMode ? 'Done selecting' : 'Select leads',
            onPressed: () => setState(() {
              _selectMode = !_selectMode;
              if (!_selectMode) _selected.clear();
            }),
            icon: Icon(_selectMode ? Icons.done_rounded : Icons.checklist_rounded),
          ),
          IconButton(
            tooltip: 'Refresh',
            onPressed: _refresh,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: SafeArea(
        top: false,
        child: ContentBounds(
          child: Column(
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
                child: TextField(
                  controller: _searchCtrl,
                  onChanged: (_) => setState(() {}),
                  decoration: InputDecoration(
                    hintText: 'Search name, company, status…',
                    prefixIcon: const Icon(Icons.search_rounded),
                    suffixIcon: _searchCtrl.text.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear_rounded),
                            onPressed: () {
                              _searchCtrl.clear();
                              setState(() {});
                            },
                          )
                        : null,
                    filled: true,
                    fillColor: AppColors.surfaceMuted,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
              ),
              if (_selectMode && _selected.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 10, 20, 0),
                  child: Row(
                    children: <Widget>[
                      Text(
                        '${_selected.length} selected',
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          color: AppColors.green,
                        ),
                      ),
                      const Spacer(),
                      TextButton(
                        onPressed: _bulkAdvance,
                        child: const Text('Advance stage'),
                      ),
                    ],
                  ),
                ),
              Expanded(
                child: FutureBuilder<List<CrmContact>>(
                  future: _future,
                  builder: (BuildContext context, AsyncSnapshot<List<CrmContact>> snap) {
                    if (snap.connectionState == ConnectionState.waiting) {
                      return const LoadingView(label: 'Pulling leads from the CRM…');
                    }
                    final List<CrmContact> all = snap.data ?? <CrmContact>[];
                    if (snap.connectionState == ConnectionState.done) {
                      _allLeads = all;
                    }
                    final List<CrmContact> leads = all
                        .where((CrmContact c) => _matchesQuery(c, _searchCtrl.text))
                        .toList();
                    if (all.isEmpty) {
                      return const EmptyState(
                        icon: Icons.people_outline_rounded,
                        title: 'No leads yet',
                        message: 'New leads you capture will land here and in your CRM repo.',
                      );
                    }
                    if (leads.isEmpty) {
                      return const EmptyState(
                        icon: Icons.search_off_rounded,
                        title: 'No matches',
                        message: 'Try a different name or company.',
                      );
                    }
                    return _LeadsList(
                      leads: leads,
                      total: all.length,
                      onRefresh: _refresh,
                      selectMode: _selectMode,
                      selected: _selected,
                      onToggleSelect: (String id) => setState(() {
                        if (_selected.contains(id)) {
                          _selected.remove(id);
                        } else {
                          _selected.add(id);
                        }
                      }),
                      onStatusTap: _showStatusSheet,
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LeadsList extends StatelessWidget {
  const _LeadsList({
    required this.leads,
    required this.total,
    required this.onRefresh,
    required this.selectMode,
    required this.selected,
    required this.onToggleSelect,
    required this.onStatusTap,
  });

  final List<CrmContact> leads;
  final int total;
  final VoidCallback onRefresh;
  final bool selectMode;
  final Set<String> selected;
  final void Function(String id) onToggleSelect;
  final void Function(CrmContact contact) onStatusTap;

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async => onRefresh(),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 14, 20, 120),
        children: <Widget>[
          MonoLabel(
            '${leads.length} shown · $total total · live from CRM',
            color: AppColors.inkSoft,
          ),
          AppSpacing.vGapMd,
          ...leads.map((CrmContact c) => Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.md),
                child: _LeadCard(
                  contact: c,
                  selectMode: selectMode,
                  isSelected: selected.contains(c.id),
                  onToggleSelect: () => onToggleSelect(c.id),
                  onStatusTap: () => onStatusTap(c),
                ),
              )),
        ].animate(interval: 50.ms).fadeIn(duration: 300.ms).slideY(begin: 0.06),
      ),
    );
  }
}

class _LeadCard extends StatelessWidget {
  const _LeadCard({
    required this.contact,
    required this.selectMode,
    required this.isSelected,
    required this.onToggleSelect,
    required this.onStatusTap,
  });

  final CrmContact contact;
  final bool selectMode;
  final bool isSelected;
  final VoidCallback onToggleSelect;
  final VoidCallback onStatusTap;

  void _open(BuildContext context) {
    if (!AppConfig.hasCrmWeb) return;
    WebViewScreen.open(
      context,
      url: AppConfig.crmWebUrl,
      title: '${contact.name} · CRM',
      desktopView: true,
    );
  }

  @override
  Widget build(BuildContext context) {
    return AppCard(
      onTap: selectMode ? onToggleSelect : () => _open(context),
      color: isSelected ? AppColors.greenSoft : AppColors.surface,
      child: Row(
        children: <Widget>[
          if (selectMode)
            Padding(
              padding: const EdgeInsets.only(right: 10),
              child: Icon(
                isSelected ? Icons.check_circle_rounded : Icons.circle_outlined,
                color: isSelected ? AppColors.green : AppColors.inkMuted,
              ),
            ),
          Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
              gradient: const LinearGradient(colors: AppColors.logoGradient),
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
            ),
            alignment: Alignment.center,
            child: Text(
              contact.name.isEmpty ? '?' : contact.name.substring(0, 1).toUpperCase(),
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  contact.name,
                  style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15),
                ),
                const SizedBox(height: 2),
                Text(
                  <String>[
                    if (contact.company.isNotEmpty) contact.company,
                    if (contact.status.isNotEmpty) contact.status,
                  ].join(' · '),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: AppColors.inkSoft, fontSize: 13),
                ),
              ],
            ),
          ),
          if (contact.value.isNotEmpty)
            Text(
              contact.value,
              style: const TextStyle(fontWeight: FontWeight.w800, color: AppColors.green),
            ),
          IconButton(
            tooltip: 'Update status',
            visualDensity: VisualDensity.compact,
            onPressed: onStatusTap,
            icon: const Icon(Icons.swap_horiz_rounded, size: 20),
          ),
          IconButton(
            tooltip: 'Prep me for a call',
            visualDensity: VisualDensity.compact,
            onPressed: () => PrepView.open(context, contact.name),
            icon: const Icon(Icons.auto_awesome_outlined, size: 20),
          ),
        ],
      ),
    );
  }
}
