from django.conf import settings
from django.db import migrations

from apps.core.rls import policy_sql


class Migration(migrations.Migration):
    dependencies = [('property', '0003_remove_bed_offers_close_at_remove_bed_offers_open_and_more'), ('maintenance', '0002_rls')]

    operations = [
        migrations.RunSQL(f'GRANT ALL ON ALL TABLES IN SCHEMA public TO {settings.DB_SYSTEM_ROLE}', migrations.RunSQL.noop),
        # the owner; whoever took it; the resident who raised the repair a photo belongs to
        policy_sql('property_photo', party_cols=('taken_by_id',),
                   extra='ticket_id IN (SELECT t.id FROM maintenance_ticket t WHERE t.raised_by_id = app_party())',
                   # anyone sees a listed PG's live photos (not repair photos)
                   public="status = 'live' AND ticket_id IS NULL AND EXISTS (SELECT 1 FROM property_property p WHERE p.id = property_id AND p.status <> 'draft')"),
    ]
