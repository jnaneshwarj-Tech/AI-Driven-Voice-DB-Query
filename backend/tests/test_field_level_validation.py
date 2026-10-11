from canonical_fields import validate_mapped_rows


def test_invalid_email_does_not_reject_student_row():
    rows = [{
        'usn': '4HG23CS032',
        'name': 'Manoj',
        'father_name': 'Rudrappa',
        'mother_name': 'Lakshmi',
        'phone': '9876543210',
        'email': '123',
        'address': 'Hassan',
        'blood_group': 'O+',
        'semester': 7,
    }]

    result = validate_mapped_rows(rows)

    assert len(result['valid']) == 1, result
    assert len(result['invalid']) == 0, result['invalid']
    assert result['valid'][0]['email'] is None
    assert 'email' in result['valid'][0].get('_field_issues', {})


def test_invalid_phone_does_not_reject_student_row():
    rows = [{
        'usn': '4HG23CS050',
        'name': 'Rahul',
        'phone': 'invalid',
        'address': 'Hassan',
        'semester': 1,
    }]

    result = validate_mapped_rows(rows)

    assert len(result['valid']) == 1, result
    assert len(result['invalid']) == 0, result['invalid']
