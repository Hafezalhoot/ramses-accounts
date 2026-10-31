"""Real two-person synthetic opening signoff for historical regression fixtures."""


def approve_all_openings(owner, owner_headers, reviewer, reviewer_headers, period):
    response = owner.get('/api/accounting/opening-reviews', params={'period': period})
    assert response.status_code == 200, response.text
    data = response.json()
    reviewer_id = next(user['id'] for user in owner.get('/api/users').json()
                       if user['username'] in ('reviewer', 'controller'))
    offset = next(account['id'] for account in data['offset_accounts'] if account['code'] == '3100')
    for fund in data['funds']:
        if fund['opening_piasters'] <= 0 or fund['review_status'] == 'approved':
            continue
        assert fund['review_status'] in (None, 'unreviewed'), fund
        grant = owner.post('/api/fund-access', headers=owner_headers, json={
            'user_id': reviewer_id, 'fund_id': fund['id'], 'can_approve': True,
            'reason': 'Independent reviewer for synthetic legacy opening test'})
        assert grant.status_code == 200, grant.text
        body = {
            'effective_date': '2025-01-01',
            'evidence_kind': {'cash': 'cash_count', 'bank': 'bank_statement',
                              'wallet': 'wallet_statement'}[fund['kind']],
            'evidence_reference': 'TEST-OPENING-' + str(fund['id']),
            'evidence_note': 'Synthetic opening proof; used for isolated regression tests only',
            'offset_account_id': offset}
        submitted = owner.post(f'/api/funds/{fund["id"]}/opening-review',
                               headers=owner_headers, json=body)
        assert submitted.status_code == 200, submitted.text
        decided = reviewer.post('/api/accounting/opening-reviews/' + str(submitted.json()['id']) + '/decision',
                                headers=reviewer_headers,
                                json={'decision': 'approve',
                                      'note': 'Independent synthetic opening signoff for regression'})
        assert decided.status_code == 200, decided.text
