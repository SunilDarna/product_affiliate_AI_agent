import datetime
import re

def parse_date(date_str):
    if not date_str:
        return None
    
    # Split by newline and take the first line to get only the date portion
    lines = [line.strip() for line in date_str.split("\n") if line.strip()]
    if not lines:
        return None
    date_str = lines[0].lower().strip()
    
    today = datetime.date.today()
    
    if "ago" in date_str:
        if "hour" in date_str or "minute" in date_str:
            return today
        elif "day" in date_str:
            try:
                days = int(re.search(r'(\d+)', date_str).group(1))
                return today - datetime.timedelta(days=days)
            except:
                return today
                
    # Normalize separators: replace commas, hyphens, and slashes with spaces
    normalized = date_str.replace(",", " ").replace("-", " ").replace("/", " ")
    # Replace multiple spaces with a single space
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }
    
    try:
        # 1. Match: Month Name, Day, Year (e.g. "dec 23 2024" or "december 23 2024")
        match = re.search(r'([a-z]{3})[a-z]*\s+(\d+)\s+(\d{4})', normalized)
        if match:
            month_name, day, year = match.groups()
            if month_name in months:
                return datetime.date(int(year), months[month_name], int(day))
                
        # 2. Match: Day, Month Name, Year (e.g. "23 dec 2024" or "23 december 2024")
        match = re.search(r'(\d+)\s+([a-z]{3})[a-z]*\s+(\d{4})', normalized)
        if match:
            day, month_name, year = match.groups()
            if month_name in months:
                return datetime.date(int(year), months[month_name], int(day))
                
        # 3. Match: Year, Month Name, Day (e.g. "2024 dec 23" or "2024 december 23")
        match = re.search(r'(\d{4})\s+([a-z]{3})[a-z]*\s+(\d+)', normalized)
        if match:
            year, month_name, day = match.groups()
            if month_name in months:
                return datetime.date(int(year), months[month_name], int(day))
                
        # 4. Match numeric: YYYY MM DD (e.g. "2024 12 23")
        match = re.search(r'^(\d{4})\s+(\d{1,2})\s+(\d{1,2})$', normalized)
        if match:
            year, month, day = match.groups()
            return datetime.date(int(year), int(month), int(day))
            
        # 5. Match numeric: DD MM YYYY (e.g. "23 12 2024") or MM DD YYYY
        match = re.search(r'^(\d{1,2})\s+(\d{1,2})\s+(\d{4})$', normalized)
        if match:
            first, second, year = match.groups()
            # If first is > 12, it must be day, and second is month
            if int(first) > 12:
                return datetime.date(int(year), int(second), int(first))
            # If second is > 12, it must be day, and first is month
            elif int(second) > 12:
                return datetime.date(int(year), int(first), int(second))
            else:
                try:
                    return datetime.date(int(year), int(second), int(first))
                except:
                    return datetime.date(int(year), int(first), int(second))
    except Exception as e:
        print(f"Error parsing date string '{date_str}' (normalized: '{normalized}'): {e}")
        
    return None

# Run tests
test_cases = [
    "23 Dec 2024\nUploaded",
    "Dec 23, 2024\nPublished",
    "23-Dec-2024",
    "23/12/2024",
    "12/23/2024",
    "2024-12-23",
    "1 day ago",
    "12 hours ago",
    "May 18, 2026",
    "18 May 2026"
]

for tc in test_cases:
    res = parse_date(tc)
    print(f"Input: {repr(tc)} => Parsed: {res}")
