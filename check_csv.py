import csv

with open('jd_tm_qa_filtered.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    total = len(rows)
    valid = sum(1 for r in rows if r.get('question', '').strip() and r.get('answer', '').strip())
    questions = [r.get('question', '').strip() for r in rows]
    unique = len(set(questions))
    print(f'总行数: {total}')
    print(f'有效行数(都有内容): {valid}')
    print(f'唯一问题数: {unique}')
    print(f'重复问题数: {total - unique}')
