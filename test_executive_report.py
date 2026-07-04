import os
import sys

# Add the project root to sys.path so we can import backend
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.report.bsa63_executive_generator import generate_report
from backend.database import get_db

def main():
    conn = get_db()
    case = conn.execute("SELECT case_id FROM cases LIMIT 1").fetchone()
    conn.close()
    
    if not case:
        print("No cases found in the database. Run a mock scan first.")
        return
        
    case_id = case["case_id"]
    print(f"Generating Executive Report for case: {case_id}")
    
    output_path = generate_report(case_id)
    print(f"Success! Report saved to: {output_path}")

if __name__ == "__main__":
    main()
