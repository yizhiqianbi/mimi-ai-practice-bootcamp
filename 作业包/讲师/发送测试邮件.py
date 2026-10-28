"""
把 13 封测试邮件发到学员的测试邮箱（作业一 C 步用）。

用法：
1. 准备一个发件邮箱（建议单独注册一个 QQ 邮箱），在 设置 → 账号 → POP3/IMAP/SMTP 服务 里开启 SMTP，拿到授权码
2. 把学员的测试邮箱地址写进 students.txt，一行一个
3. 运行：
   python3 发送测试邮件.py --sender 你的发件邮箱@qq.com --code 授权码 --to students.txt
   先加 --dry-run 看一遍要发什么

说明：
- 邮件的发件人显示名会保留原样（如「林小姐」），但实际发件地址是你的发件邮箱，回复地址设为原邮件里的虚构地址
- 每封之间间隔几秒，避免被当成垃圾邮件；20 个学员 × 13 封约 15 分钟
- QQ 邮箱单日发信有上限，学员多的话分两天发或用两个发件邮箱
"""
import argparse, email, glob, os, smtplib, time
from email import policy
from email.message import EmailMessage
from email.utils import formataddr

HERE = os.path.dirname(os.path.abspath(__file__))
MAIL_DIR = os.path.join(HERE, '..', '作业一-知识库与邮件助理', '示例邮件')

ap = argparse.ArgumentParser()
ap.add_argument('--sender', required=True)
ap.add_argument('--code', help='SMTP 授权码')
ap.add_argument('--to', required=True, help='学员邮箱列表文件，一行一个')
ap.add_argument('--host', default='smtp.qq.com')
ap.add_argument('--port', type=int, default=465)
ap.add_argument('--gap', type=float, default=3, help='每封间隔秒数')
ap.add_argument('--dry-run', action='store_true')
a = ap.parse_args()

students = [x.strip() for x in open(a.to, encoding='utf-8') if x.strip() and not x.startswith('#')]
mails = []
for f in sorted(glob.glob(os.path.join(MAIL_DIR, '*.eml'))):
    m = email.message_from_bytes(open(f, 'rb').read(), policy=policy.default)
    frm = m['From'].addresses[0]
    mails.append((frm.display_name, frm.addr_spec, str(m['Subject']), m.get_body(('plain',)).get_content()))
print(f'{len(students)} 个学员 × {len(mails)} 封邮件')

if a.dry_run:
    for n, addr, subj, _ in mails: print(f'  {n} <{addr}>｜{subj}')
    raise SystemExit

s = smtplib.SMTP_SSL(a.host, a.port); s.login(a.sender, a.code)
for to in students:
    for name, addr, subj, body in mails:
        msg = EmailMessage()
        msg['From'] = formataddr((name, a.sender)); msg['Reply-To'] = addr; msg['To'] = to; msg['Subject'] = subj
        msg.set_content(body)
        s.send_message(msg); print('已发', to, subj); time.sleep(a.gap)
s.quit()
