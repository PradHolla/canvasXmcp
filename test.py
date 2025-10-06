import requests
import json
from typing import Dict, List, Tuple
from dotenv import load_dotenv
import os

class CanvasTokenVerifier:
    def __init__(self, canvas_url: str, access_token: str):
        """
        Initialize Canvas API token verifier
        
        Args:
            canvas_url: Your Canvas instance URL (e.g., 'https://canvas.instructure.com')
            access_token: Your Canvas API access token
        """
        self.base_url = canvas_url.rstrip('/')
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        self.test_results = []
    
    def test_endpoint(self, name: str, endpoint: str, method: str = 'GET') -> Tuple[bool, str]:
        """Test a single API endpoint"""
        url = f"{self.base_url}/api/v1/{endpoint}"
        try:
            if method == 'GET':
                response = requests.get(url, headers=self.headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                return True, f"✓ {name}: SUCCESS"
            elif response.status_code == 401:
                return False, f"✗ {name}: UNAUTHORIZED - Invalid or expired token"
            elif response.status_code == 403:
                return False, f"✗ {name}: FORBIDDEN - Insufficient permissions"
            elif response.status_code == 404:
                return False, f"⚠ {name}: NOT FOUND - Endpoint may not exist or no data available"
            else:
                return False, f"⚠ {name}: HTTP {response.status_code} - {response.text[:100]}"
        except requests.exceptions.RequestException as e:
            return False, f"✗ {name}: CONNECTION ERROR - {str(e)}"
    
    def verify_all_capabilities(self) -> Dict:
        """Test all essential Canvas API capabilities for the project"""
        
        print("=" * 70)
        print("CANVAS API TOKEN VERIFICATION")
        print("=" * 70)
        print()
        
        # Test 1: Basic Authentication
        print("📋 Testing Basic Authentication...")
        success, msg = self.test_endpoint("Current User", "users/self")
        print(f"  {msg}")
        self.test_results.append(("Authentication", success))
        
        if not success:
            print("\n❌ CRITICAL: Cannot authenticate. Check your token and Canvas URL.")
            return self.generate_report()
        
        print()
        
        # Test 2: Courses Access
        print("📚 Testing Courses Access...")
        success, msg = self.test_endpoint("List Courses", "courses")
        print(f"  {msg}")
        self.test_results.append(("Courses", success))
        print()
        
        # Test 3: Assignments Access
        print("📝 Testing Assignments Access...")
        # First get a course ID
        try:
            courses_response = requests.get(
                f"{self.base_url}/api/v1/courses",
                headers=self.headers,
                timeout=10
            )
            if courses_response.status_code == 200 and courses_response.json():
                course_id = courses_response.json()[0]['id']
                success, msg = self.test_endpoint(
                    "List Assignments",
                    f"courses/{course_id}/assignments"
                )
                print(f"  {msg}")
                self.test_results.append(("Assignments", success))
            else:
                print("  ⚠ Cannot test assignments - no courses found")
                self.test_results.append(("Assignments", False))
        except Exception as e:
            print(f"  ✗ Assignments: ERROR - {str(e)}")
            self.test_results.append(("Assignments", False))
        print()
        
        # Test 4: Submissions Access
        print("📤 Testing Submissions Access...")
        try:
            if courses_response.status_code == 200 and courses_response.json():
                course_id = courses_response.json()[0]['id']
                success, msg = self.test_endpoint(
                    "List Submissions",
                    f"courses/{course_id}/students/submissions"
                )
                print(f"  {msg}")
                self.test_results.append(("Submissions", success))
            else:
                print("  ⚠ Cannot test submissions - no courses found")
                self.test_results.append(("Submissions", False))
        except Exception as e:
            print(f"  ✗ Submissions: ERROR - {str(e)}")
            self.test_results.append(("Submissions", False))
        print()
        
        # Test 5: Announcements Access
        # Test 5: Announcements Access
        print("📢 Testing Announcements Access...")
        try:
            if courses_response.status_code == 200 and courses_response.json():
                courses = courses_response.json()
                
                # Test with first course
                course_id = courses[0]['id']
                endpoint = f"announcements?context_codes[]=course_{course_id}"
                
                response = requests.get(
                    f"{self.base_url}/api/v1/{endpoint}",
                    headers=self.headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    announcements = response.json()
                    print(f"  ✓ List Announcements: SUCCESS (found {len(announcements)} announcements)")
                    self.test_results.append(("Announcements", True))
                else:
                    print(f"  ⚠ List Announcements: HTTP {response.status_code}")
                    self.test_results.append(("Announcements", False))
            else:
                print("  ⚠ Cannot test announcements - no courses found")
                self.test_results.append(("Announcements", False))
        except Exception as e:
            print(f"  ✗ Announcements: ERROR - {str(e)}")
            self.test_results.append(("Announcements", False))
        print()

        
        # Test 6: Calendar Events
        print("📅 Testing Calendar Access...")
        success, msg = self.test_endpoint("List Calendar Events", "calendar_events")
        print(f"  {msg}")
        self.test_results.append(("Calendar", success))
        print()
        
        # Test 7: Discussions/Forums
        print("💬 Testing Discussions Access...")
        try:
            if courses_response.status_code == 200 and courses_response.json():
                course_id = courses_response.json()[0]['id']
                success, msg = self.test_endpoint(
                    "List Discussion Topics",
                    f"courses/{course_id}/discussion_topics"
                )
                print(f"  {msg}")
                self.test_results.append(("Discussions", success))
            else:
                print("  ⚠ Cannot test discussions - no courses found")
                self.test_results.append(("Discussions", False))
        except Exception as e:
            print(f"  ✗ Discussions: ERROR - {str(e)}")
            self.test_results.append(("Discussions", False))
        print()
        
        # Test 8: Files Access
        print("📁 Testing Files Access...")
        success, msg = self.test_endpoint("List User Files", "users/self/files")
        print(f"  {msg}")
        self.test_results.append(("Files", success))
        print()
        
        # Test 9: Modules Access
        print("📖 Testing Modules Access...")
        try:
            if courses_response.status_code == 200 and courses_response.json():
                course_id = courses_response.json()[0]['id']
                success, msg = self.test_endpoint(
                    "List Modules",
                    f"courses/{course_id}/modules"
                )
                print(f"  {msg}")
                self.test_results.append(("Modules", success))
            else:
                print("  ⚠ Cannot test modules - no courses found")
                self.test_results.append(("Modules", False))
        except Exception as e:
            print(f"  ✗ Modules: ERROR - {str(e)}")
            self.test_results.append(("Modules", False))
        print()
        
        # Test 10: User Profile
        print("👤 Testing User Profile Access...")
        success, msg = self.test_endpoint("User Profile", "users/self/profile")
        print(f"  {msg}")
        self.test_results.append(("Profile", success))
        print()
        
        return self.generate_report()
    
    def generate_report(self) -> Dict:
        """Generate final verification report"""
        print("=" * 70)
        print("VERIFICATION SUMMARY")
        print("=" * 70)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for _, success in self.test_results if success)
        
        print(f"\nTests Passed: {passed_tests}/{total_tests}")
        print()
        
        if passed_tests == total_tests:
            print("✅ EXCELLENT! Your token has all necessary permissions.")
            print("   You can proceed with the project.")
            status = "READY"
        elif passed_tests >= total_tests * 0.7:
            print("⚠️  PARTIAL ACCESS: Some features may not work.")
            print("   Review failed tests and consider requesting additional permissions.")
            status = "PARTIAL"
        else:
            print("❌ INSUFFICIENT ACCESS: Your token lacks critical permissions.")
            print("   You may need to regenerate your token or contact your Canvas admin.")
            status = "BLOCKED"
        
        print("\n" + "=" * 70)
        
        return {
            "status": status,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "results": self.test_results
        }


# Usage Example
if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()

    # Get Canvas instance URL and access token from environment variables
    CANVAS_URL = os.getenv("CANVAS_URL")
    ACCESS_TOKEN = os.getenv("CANVAS_API_TOKEN")

    # Verify token
    verifier = CanvasTokenVerifier(CANVAS_URL, ACCESS_TOKEN)
    report = verifier.verify_all_capabilities()
    
    # Optional: Save results to file
    with open('canvas_token_verification.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    print("\n📄 Results saved to 'canvas_token_verification.json'")
