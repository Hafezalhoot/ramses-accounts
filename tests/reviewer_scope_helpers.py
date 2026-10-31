"""Legacy regression fixture: explicitly grant reviewers the test billing stations.

Production reviewers NEVER receive these assignments automatically; only the
isolated historical test scenarios use this helper to set up their expected role.
"""

def grant_reviewers_for_test(owner, headers):
    users = owner.get('/api/users').json()
    points = owner.get('/api/billing/config').json()['points']
    for user in users:
        if user['role'] == 'reviewer' and user['active']:
            for point in points:
                r = owner.post(f"/api/billing/points/{point['id']}/assign",
                               headers=headers, json={'user_id': user['id'], 'active': True})
                assert r.status_code == 200, r.text
