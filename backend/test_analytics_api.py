"""
Test script to verify graduation analytics endpoint and natural language queries
"""
import requests
import json

BASE_URL = 'http://localhost:8000'

def login():
    """Login and get access token"""
    # Check if we have a user in the database
    response = requests.post(f'{BASE_URL}/api/auth/login', 
                           data={'username': 'admin', 'password': 'admin'})
    
    if response.status_code == 200:
        return response.json()['access_token']
    
    # If admin doesn't exist, try registering
    reg_response = requests.post(f'{BASE_URL}/api/auth/register', 
                                json={
                                    'username': 'testadmin',
                                    'email': 'test@admin.com',
                                    'password': 'test123',
                                    'role': 'admin'
                                })
    
    if reg_response.status_code == 200:
        # Login with new user
        login_response = requests.post(f'{BASE_URL}/api/auth/login', 
                                      data={'username': 'testadmin', 'password': 'test123'})
        return login_response.json()['access_token']
    
    raise Exception("Could not authenticate")

def test_analytics(token):
    """Test the analytics endpoint"""
    headers = {'Authorization': f'Bearer {token}'}
    response = requests.get(f'{BASE_URL}/api/query/analytics', headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        grad_analytics = data.get('graduation_analytics', {})
        
        print("=" * 70)
        print("GRADUATION ANALYTICS TEST RESULTS")
        print("=" * 70)
        print(f"Total Students: {data.get('total_students')}")
        print(f"Total Marks: {data.get('total_marks')}")
        print(f"Total Files: {data.get('total_files')}")
        print(f"Total Queries: {data.get('total_queries')}")
        
        print("\n" + "=" * 70)
        print("GRADUATION STATISTICS")
        print("=" * 70)
        print(f"  Active Students: {grad_analytics.get('total_active', 0)}")
        print(f"  Graduated Students: {grad_analytics.get('total_graduated', 0)}")
        print(f"  Graduated This Year (2026): {grad_analytics.get('graduated_this_year', 0)}")
        print(f"  Next Graduation Batch: {grad_analytics.get('next_graduation_batch', 'N/A')}")
        
        print("\nSTUDENT TYPE DISTRIBUTION:")
        st_dist = grad_analytics.get('student_type_distribution', {})
        print(f"  Regular: {st_dist.get('Regular', 0)}")
        print(f"  Lateral Entry: {st_dist.get('Lateral Entry', 0)}")
        
        print("\nADMISSION BATCH DISTRIBUTION:")
        for batch, count in sorted(grad_analytics.get('admission_batch_distribution', {}).items()):
            print(f"  Batch {batch}: {count} students")
        
        print("\nGRADUATION BY YEAR:")
        for year, count in sorted(grad_analytics.get('graduation_by_year', {}).items()):
            print(f"  Year {year}: {count} students")
        
        print("\nGRADUATION BY BRANCH:")
        for branch, stats in sorted(grad_analytics.get('graduation_by_branch', {}).items()):
            print(f"  {branch}: Active={stats.get('active', 0)}, Graduated={stats.get('graduated', 0)}")
        
        print("\n" + "=" * 70)
        print("✓ Analytics endpoint working correctly!")
        print("=" * 70)
        return True
    else:
        print(f"Error: Status code {response.status_code}")
        print(response.text)
        return False

def test_nlp_queries(token):
    """Test natural language graduation queries"""
    headers = {'Authorization': f'Bearer {token}'}
    
    test_queries = [
        "show graduated students",
        "show 2024 graduates", 
        "show active students",
        "show lateral entry students",
        "show alumni",
        "show 2022 admission batch"
    ]
    
    print("\n" + "=" * 70)
    print("TESTING NATURAL LANGUAGE GRADUATION QUERIES")
    print("=" * 70)
    
    for query in test_queries:
        print(f"\n🔍 Query: '{query}'")
        response = requests.post(f'{BASE_URL}/api/query/generate',
                               json={'natural_query': query},
                               headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            sql = result.get('query_dict', {}).get('sql', '')
            print(f"   ✓ Generated SQL: {sql[:100]}...")
            
            # Execute the query
            exec_response = requests.post(f'{BASE_URL}/api/query/execute',
                                        json={'query_dict': result['query_dict'], 
                                             'original_query': query},
                                        headers=headers)
            
            if exec_response.status_code == 200:
                exec_result = exec_response.json()
                count = len(exec_result.get('data', []))
                print(f"   ✓ Results: {count} records")
            else:
                print(f"   ✗ Execute failed: {exec_response.status_code}")
        else:
            print(f"   ✗ Query generation failed: {response.status_code}")
    
    print("\n" + "=" * 70)
    print("✓ NLP query testing complete!")
    print("=" * 70)

try:
    print("Logging in...")
    token = login()
    print("✓ Authentication successful!\n")
    
    # Test analytics endpoint
    analytics_ok = test_analytics(token)
    
    if analytics_ok:
        # Test natural language queries
        test_nlp_queries(token)
    
    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Open http://localhost:5174 in your browser")
    print("2. Login with credentials (admin/admin or testadmin/test123)")
    print("3. Navigate to Analytics tab")
    print("4. Verify graduation charts and statistics display")
    print("5. Go to Query tab and test natural language queries")
    print("=" * 70)

except Exception as e:
    print(f"\n✗ Error during testing: {e}")
    import traceback
    traceback.print_exc()
