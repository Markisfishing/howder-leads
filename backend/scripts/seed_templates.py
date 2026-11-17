"""初版郵件模板種子（M2-02c）。

執行：uv run python -m scripts.seed_templates
已經有同名模板就不再新增（可以重複執行）。正式文字等 SPEC 11-5 由業務／法務提供，
到時候在 /admin/templates 修改即可（會新增版本，不會覆蓋）。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.domain import template_rules
from app.models import EmailTemplate

SEED_NAME = "初版邀請信（佔位文字，待 SPEC 11-5 確認）"
SEED_SUBJECT = "厚達電子端子台｜{{company_name}} 合作邀請"
SEED_BODY = """{{contact_name}} 您好：

我是厚達電子業務部的 {{sender_name}}。厚達電子專注於端子台的設計與製造，產品可以用在控制盤、配電與設備配線。

{{ai_paragraph}}

想請教 {{company_name}} 在端子台方面是否有採購或替代的需求，我們可以提供型錄與樣品。

方便的話，請直接回覆這封信，或告訴我適合聯絡的時間。

{{sender_name}}
厚達電子 業務部
{{sender_email}}

{{unsubscribe}}"""


def seed(db: Session) -> bool:
    """新增種子模板；已經有同名的就跳過。回傳是否有新增。"""
    if db.scalar(select(EmailTemplate).where(EmailTemplate.name == SEED_NAME)) is not None:
        return False
    template_rules.validate_template(SEED_SUBJECT, SEED_BODY)
    t = EmailTemplate(
        name=SEED_NAME,
        subject=SEED_SUBJECT,
        body_text=SEED_BODY,
        body_html=template_rules.text_to_html(SEED_BODY),
        version=1,
        is_active=True,
    )
    db.add(t)
    db.flush()
    t.family_id = t.template_id
    db.commit()
    return True


if __name__ == "__main__":
    with Session(get_engine()) as session:
        print("已新增初版模板" if seed(session) else "初版模板已存在，略過")
