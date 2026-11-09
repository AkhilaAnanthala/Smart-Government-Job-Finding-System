"""
seed_data.py
Creates the database (if needed) and inserts demo/sample data.

Usage (from the project folder, with the venv active):
    python seed_data.py            -> add sample data (skips what already exists)
    python seed_data.py --reset    -> DELETE everything and rebuild from scratch

IMPORTANT: all jobs and questions here are DEMONSTRATION data, not official.
"""
import sys
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from db import standalone_db, init_db, query_db, execute_db

TODAY = date.today()


def day(offset):
    """Date string (YYYY-MM-DD) offset days from today."""
    return (TODAY + timedelta(days=offset)).isoformat()


# ====================================================================
# 1. EXAMS
# (name, short_code, category, conducting_body, govt_level,
#  description, exam_pattern, syllabus_summary, official_url)
# ====================================================================
SSC_SYLLABUS_URL = "https://ssc.gov.in/for-candidates/syllabus"
VERIFY = " Verify the current scheme in the latest official notification."

EXAMS = [
    ("UPSC Civil Services Examination", "UPSC-CSE", "UPSC", "Union Public Service Commission", "Central",
     "Recruitment to top civil services such as IAS, IPS and IFS.",
     "Three stages: Preliminary (objective, 2 papers; the aptitude paper is qualifying), Main (written), "
     "and Interview. Prelims has negative marking." + VERIFY,
     "Indian polity, history, geography, economy, environment, science and technology, current affairs, "
     "and aptitude.",
     "https://upsc.gov.in/"),
    ("SSC Combined Graduate Level", "SSC-CGL", "SSC", "Staff Selection Commission", "Central",
     "Graduate-level posts in central government ministries, departments and offices.",
     "Computer-based tiers testing reasoning, quantitative aptitude, English and general awareness." + VERIFY,
     "Reasoning, quantitative aptitude, English language, general awareness.",
     SSC_SYLLABUS_URL),
    ("SSC Combined Higher Secondary Level", "SSC-CHSL", "SSC", "Staff Selection Commission", "Central",
     "12th-pass level clerical and data entry posts in central government offices.",
     "Computer-based Tier-I followed by a skill/typing test as applicable." + VERIFY,
     "Reasoning, quantitative aptitude, English language, general awareness.",
     SSC_SYLLABUS_URL),
    ("SSC Multi Tasking Staff", "SSC-MTS", "SSC", "Staff Selection Commission", "Central",
     "10th-pass level support staff posts in central government offices.",
     "Computer-based test, with further stages as applicable." + VERIFY,
     "Numerical aptitude, reasoning, general awareness, English language.",
     SSC_SYLLABUS_URL),
    ("RRB Non-Technical Popular Categories", "RRB-NTPC", "Railway", "Railway Recruitment Boards", "Central",
     "Graduate and 12th-level non-technical posts in Indian Railways.",
     "Computer-based tests (CBT-1, CBT-2), then typing/aptitude test or document verification as applicable."
     + VERIFY,
     "Mathematics, general intelligence and reasoning, general awareness.",
     None),
    ("RRB Group D", "RRB-GROUP-D", "Railway", "Railway Recruitment Boards", "Central",
     "10th-pass / ITI level posts in Indian Railways.",
     "Computer-based test, physical efficiency test and document verification." + VERIFY,
     "Mathematics, general intelligence and reasoning, general science, general awareness.",
     None),
    ("APPSC Group-I Services", "APPSC-G1", "APPSC", "Andhra Pradesh Public Service Commission",
     "Andhra Pradesh",
     "Senior state administrative services of the Andhra Pradesh government.",
     "Preliminary screening test, Main written examination and interview as per notification." + VERIFY,
     "General studies, Indian and Andhra Pradesh history, polity, economy, geography, current affairs.",
     "https://portal-psc.ap.gov.in/"),
    ("APPSC Group-II Services", "APPSC-G2", "APPSC", "Andhra Pradesh Public Service Commission",
     "Andhra Pradesh",
     "State executive and non-executive posts of the Andhra Pradesh government.",
     "Screening test and Main written examination as per notification." + VERIFY,
     "General studies, mental ability, Andhra Pradesh history, polity and economy.",
     "https://portal-psc.ap.gov.in/"),
    ("AP Teacher Recruitment Test (DSC)", "AP-DSC", "Other", "School Education Department, Andhra Pradesh",
     "Andhra Pradesh",
     "Teacher recruitment in Andhra Pradesh government schools.",
     "Written recruitment test; weightage of eligibility test scores as per notification." + VERIFY,
     "Child development and pedagogy, subject content, general knowledge.",
     None),
]

# ====================================================================
# 2. SUBJECTS   exam_code -> [(subject name, description), ...]
# ====================================================================
SUBJECTS = {
    "UPSC-CSE": [("Indian Polity", "Constitution, parliament, governance."),
                 ("CSAT (Aptitude)", "Comprehension, reasoning and basic numeracy.")],
    "SSC-CGL": [("General Awareness", "Static GK, polity, science and current affairs."),
                ("Quantitative Aptitude", "Arithmetic and basic mathematics."),
                ("General Intelligence & Reasoning", "Series, analogies, coding and logic."),
                ("English Language", "Vocabulary, grammar and comprehension.")],
    "SSC-CHSL": [("General Awareness", "Static GK, polity, science and current affairs."),
                 ("Quantitative Aptitude", "Arithmetic and basic mathematics."),
                 ("General Intelligence & Reasoning", "Series, analogies, coding and logic."),
                 ("English Language", "Vocabulary, grammar and comprehension.")],
    "SSC-MTS": [("General Awareness", "Static GK and current affairs."),
                ("Numerical Aptitude", "Basic arithmetic.")],
    "RRB-NTPC": [("Mathematics", "Arithmetic and geometry basics."),
                 ("General Awareness", "Railways, science, polity and current affairs.")],
    "RRB-GROUP-D": [("Mathematics", "Arithmetic basics."),
                    ("General Science", "Class 10 level physics, chemistry, biology.")],
    "APPSC-G1": [("General Studies", "Indian and Andhra Pradesh general studies.")],
    "APPSC-G2": [("General Studies", "Andhra Pradesh and Indian general studies.")],
    "AP-DSC": [("Child Development and Pedagogy", "Teaching and learning basics.")],
}

# ====================================================================
# 3. JOBS (ALL DEMO RECORDS)
# Fields: title, organization, govt, exam_category, qualification text, level,
#         min_age, max_age, state_requirement, vacancies, start_offset,
#         deadline_offset, salary, exam_codes, link_key
# Offsets are days from today, so deadlines never go stale.
# ====================================================================
LINKS = {
    "UPSC": "https://upsc.gov.in/",
    "SSC": "https://ssc.gov.in/",
    "APPSC": "https://portal-psc.ap.gov.in/",
    None: None,
}
SAL = " (sample range; verify in official notification)"

JOBS = [
    ("Civil Services Officer (IAS/IPS/IFS and allied) - Demo", "Union Public Service Commission (UPSC)",
     "Central", "UPSC", "Bachelor's degree from a recognised university", 4, 21, 32, None, 100, -20, 25,
     "Senior pay levels" + SAL, ["UPSC-CSE"], "UPSC"),
    ("Assistant Section Officer - Demo", "Staff Selection Commission (SSC)", "Central", "SSC",
     "Bachelor's degree from a recognised university", 4, 20, 30, None, 300, -15, 12,
     "Mid pay levels" + SAL, ["SSC-CGL"], "SSC"),
    ("Inspector (Taxation) - Demo", "Staff Selection Commission (SSC)", "Central", "SSC",
     "Bachelor's degree from a recognised university", 4, 18, 30, None, 250, -15, 12,
     "Mid pay levels" + SAL, ["SSC-CGL"], "SSC"),
    ("Auditor - Demo", "Staff Selection Commission (SSC)", "Central", "SSC",
     "Bachelor's degree from a recognised university", 4, 18, 27, None, 400, -15, 12,
     "Mid pay levels" + SAL, ["SSC-CGL"], "SSC"),
    ("Statistical Investigator Grade-II - Demo", "Staff Selection Commission (SSC)", "Central", "SSC",
     "Master's degree (Statistics or related subject)", 5, 18, 32, None, 60, -10, 20,
     "Mid pay levels" + SAL, ["SSC-CGL"], "SSC"),
    ("Lower Division Clerk / Junior Secretariat Assistant - Demo", "Staff Selection Commission (SSC)",
     "Central", "SSC", "12th pass (Intermediate)", 2, 18, 27, None, 500, -12, 30,
     "Entry pay levels" + SAL, ["SSC-CHSL"], "SSC"),
    ("Data Entry Operator - Demo", "Staff Selection Commission (SSC)", "Central", "SSC",
     "12th pass (Intermediate) with Science/Maths as per notification", 2, 18, 27, None, 150, -12, 30,
     "Entry pay levels" + SAL, ["SSC-CHSL"], "SSC"),
    ("Multi Tasking Staff (Non-Technical) - Demo", "Staff Selection Commission (SSC)", "Central", "SSC",
     "10th pass", 1, 18, 25, None, 800, -5, 40,
     "Entry pay levels" + SAL, ["SSC-MTS"], "SSC"),
    ("Station Master - Demo", "Railway Recruitment Boards (RRB)", "Central", "Railway",
     "Bachelor's degree from a recognised university", 4, 18, 33, None, 200, -8, 18,
     "Mid pay levels" + SAL, ["RRB-NTPC"], None),
    ("Junior Clerk cum Typist - Demo", "Railway Recruitment Boards (RRB)", "Central", "Railway",
     "12th pass (Intermediate)", 2, 18, 30, None, 350, -8, 18,
     "Entry pay levels" + SAL, ["RRB-NTPC"], None),
    ("Commercial cum Ticket Clerk - Demo", "Railway Recruitment Boards (RRB)", "Central", "Railway",
     "12th pass (Intermediate)", 2, 18, 30, None, 300, -8, 18,
     "Entry pay levels" + SAL, ["RRB-NTPC"], None),
    ("Track Maintainer (Group D) - Demo", "Railway Recruitment Boards (RRB)", "Central", "Railway",
     "10th pass or ITI", 1, 18, 33, None, 1000, -30, -10,
     "Entry pay levels" + SAL, ["RRB-GROUP-D"], None),   # deadline already passed (to test 'closed')
    ("Deputy Collector Level Post (Group-I) - Demo", "Andhra Pradesh Public Service Commission (APPSC)",
     "Andhra Pradesh", "APPSC", "Bachelor's degree from a recognised university", 4, 18, 42, None, 40,
     -10, 35, "State pay scale" + SAL, ["APPSC-G1"], "APPSC"),
    ("Group-II Executive Post - Demo", "Andhra Pradesh Public Service Commission (APPSC)",
     "Andhra Pradesh", "APPSC", "Bachelor's degree from a recognised university", 4, 18, 42, None, 150,
     -10, 28, "State pay scale" + SAL, ["APPSC-G2"], "APPSC"),
    ("Secondary Grade Teacher - Demo", "School Education Department, Government of Andhra Pradesh",
     "Andhra Pradesh", "Other", "12th pass with D.El.Ed (or equivalent teacher training)", 3, 18, 44,
     "Andhra Pradesh", 500, -5, 22, "State pay scale" + SAL, ["AP-DSC"], None),
]

# ====================================================================
# 4. OFFICIAL RESOURCES (only the links you provided)
# (title, url, description, kind, exam_code or None)
# ====================================================================
OFFICIAL_RESOURCES = [
    ("APPSC Official Portal", "https://portal-psc.ap.gov.in/",
     "Official portal of the Andhra Pradesh Public Service Commission.", "Portal", None),
    ("APPSC Mock Tests (external site)", "https://portal-psc.ap.gov.in/HomePages/MockTest",
     "Mock tests hosted by APPSC. This opens the official external website; this portal does not host it.",
     "Mock Test", None),
    ("APPSC Syllabus and Old Question Papers", "https://portal-psc.ap.gov.in/HomePages/GroupsSyllabus",
     "Group-wise syllabus and old question papers on the APPSC portal.", "Syllabus", None),
    ("UPSC Previous Question Papers", "https://www.upsc.gov.in/examinations/previous-question-papers",
     "Previous question papers published by UPSC.", "Previous Papers", "UPSC-CSE"),
    ("SSC Syllabus", SSC_SYLLABUS_URL,
     "Syllabus information for SSC examinations.", "Syllabus", None),
]

# ====================================================================
# 5. PREVIOUS PAPERS (links only; (exam_code, title, year, url, is_official))
# ====================================================================
PREVIOUS_PAPERS = [
    ("UPSC-CSE", "UPSC previous question papers (official page)", None,
     "https://www.upsc.gov.in/examinations/previous-question-papers", 1),
    ("APPSC-G1", "APPSC syllabus and old question papers (official page)", None,
     "https://portal-psc.ap.gov.in/HomePages/GroupsSyllabus", 1),
    ("APPSC-G2", "APPSC syllabus and old question papers (official page)", None,
     "https://portal-psc.ap.gov.in/HomePages/GroupsSyllabus", 1),
]

# ====================================================================
# 6. STUDY MATERIALS (government sources only)
# (exam_code, subject, title, description, type, url, is_official)
# Admins can add more (including PDFs) from the admin dashboard.
# ====================================================================
NCERT = "https://ncert.nic.in/textbook.php"
STUDY_MATERIALS = [
    ("UPSC-CSE", "Indian Polity", "NCERT Textbooks (free, official)",
     "Free NCERT textbooks. Useful for building basics in polity and other subjects.", "Link", NCERT, 1),
    ("UPSC-CSE", "Indian Polity", "Constitution of India - India Code portal",
     "Government portal for central acts and the Constitution of India.", "Link",
     "https://www.indiacode.nic.in/", 1),
    ("SSC-CGL", "General Awareness", "NCERT Textbooks (free, official)",
     "Class-level science and social science basics for general awareness.", "Link", NCERT, 1),
    ("SSC-CGL", "General Awareness", "SSC Syllabus (official)",
     "Official SSC syllabus page.", "Link", SSC_SYLLABUS_URL, 1),
    ("RRB-NTPC", "Mathematics", "NCERT Mathematics Textbooks (free, official)",
     "Foundation mathematics for school-level arithmetic.", "Link", NCERT, 1),
    ("APPSC-G2", "General Studies", "APPSC Syllabus and Old Question Papers (official)",
     "Official APPSC page for syllabus and old question papers.", "Link",
     "https://portal-psc.ap.gov.in/HomePages/GroupsSyllabus", 1),
]

# ====================================================================
# 7. PRACTICE QUESTIONS (80 original questions, DEMO)
# Format: (question, [A, B, C, D], correct letter, explanation, difficulty)
# ====================================================================
QUESTIONS = {
    ("SSC-CGL", "General Awareness"): [
        ("Who was the first President of India?", ["Dr. S. Radhakrishnan", "Dr. Rajendra Prasad", "Dr. Zakir Husain", "V. V. Giri"], "B",
         "Dr. Rajendra Prasad served as the first President of India (1950-1962).", "Easy"),
        ("Which gas forms the largest part of Earth's atmosphere?", ["Oxygen", "Carbon dioxide", "Nitrogen", "Argon"], "C",
         "Nitrogen makes up about 78% of the atmosphere.", "Easy"),
        ("What is the national animal of India?", ["Lion", "Tiger", "Elephant", "Leopard"], "B",
         "The Bengal tiger is India's national animal.", "Easy"),
        ("Which river is known as the 'Sorrow of Bihar'?", ["Ganga", "Gandak", "Son", "Kosi"], "D",
         "The Kosi frequently changes course and causes floods in Bihar.", "Medium"),
        ("Where is the headquarters of the Reserve Bank of India located?", ["Mumbai", "New Delhi", "Kolkata", "Chennai"], "A",
         "The RBI's central office is in Mumbai.", "Easy"),
        ("Deficiency of which vitamin causes scurvy?", ["Vitamin A", "Vitamin B12", "Vitamin C", "Vitamin D"], "C",
         "Scurvy is caused by a lack of Vitamin C.", "Easy"),
        ("Which Article of the Indian Constitution abolishes untouchability?", ["Article 14", "Article 15", "Article 16", "Article 17"], "D",
         "Article 17 abolishes untouchability and forbids its practice.", "Medium"),
        ("What is the SI unit of force?", ["Joule", "Newton", "Pascal", "Watt"], "B",
         "Force is measured in newtons (N).", "Easy"),
        ("Who wrote the book 'The Discovery of India'?", ["Mahatma Gandhi", "Sardar Patel", "Jawaharlal Nehru", "B. R. Ambedkar"], "C",
         "Jawaharlal Nehru wrote it while in prison in 1944.", "Medium"),
        ("Which is the largest planet in the Solar System?", ["Saturn", "Jupiter", "Neptune", "Earth"], "B",
         "Jupiter is the largest planet.", "Easy"),
    ],
    ("SSC-CGL", "Quantitative Aptitude"): [
        ("What is 15% of 200?", ["20", "25", "30", "35"], "C", "15/100 x 200 = 30.", "Easy"),
        ("Find the simple interest on Rs. 1000 at 5% per year for 2 years.", ["Rs. 50", "Rs. 100", "Rs. 150", "Rs. 200"], "B",
         "SI = (P x R x T)/100 = (1000 x 5 x 2)/100 = 100.", "Easy"),
        ("What is the average of 10, 20, 30, 40 and 50?", ["25", "30", "35", "40"], "B",
         "Sum = 150, and 150 / 5 = 30.", "Easy"),
        ("A train runs at 60 km/h. How far does it travel in 2.5 hours?", ["120 km", "140 km", "150 km", "180 km"], "C",
         "Distance = speed x time = 60 x 2.5 = 150 km.", "Easy"),
        ("What is the LCM of 12 and 18?", ["24", "36", "54", "72"], "B",
         "12 = 2^2 x 3 and 18 = 2 x 3^2, so LCM = 2^2 x 3^2 = 36.", "Medium"),
        ("Two numbers are in the ratio 3:5 and their sum is 64. What is the larger number?", ["24", "32", "40", "44"], "C",
         "Total parts = 8, so one part = 8. Larger number = 5 x 8 = 40.", "Medium"),
        ("What is the area of a rectangle of length 12 m and breadth 8 m?", ["40 sq m", "80 sq m", "96 sq m", "100 sq m"], "C",
         "Area = length x breadth = 12 x 8 = 96.", "Easy"),
        ("What is the square root of 1764?", ["38", "42", "44", "48"], "B", "42 x 42 = 1764.", "Medium"),
        ("If x + 5 = 12, what is the value of 2x?", ["7", "12", "14", "17"], "C", "x = 7, so 2x = 14.", "Easy"),
        ("An article bought for Rs. 800 is sold for Rs. 1000. What is the profit percentage?", ["20%", "25%", "30%", "35%"], "B",
         "Profit = 200, and 200/800 x 100 = 25%.", "Medium"),
    ],
    ("SSC-CGL", "General Intelligence & Reasoning"): [
        ("Find the next number: 2, 4, 8, 16, ?", ["24", "30", "32", "64"], "C", "Each number is double the previous one.", "Easy"),
        ("Which one is the odd one out: Apple, Mango, Potato, Banana?", ["Apple", "Mango", "Potato", "Banana"], "C",
         "Potato is a vegetable (root); the others are fruits.", "Easy"),
        ("A woman points to a man and says, 'His mother is the only daughter of my mother.' How is the man related to the woman?",
         ["Brother", "Son", "Nephew", "Cousin"], "B", "The only daughter of her mother is the woman herself, so the man is her son.", "Medium"),
        ("Find the next letter: A, C, E, G, ?", ["H", "I", "J", "K"], "B", "Letters skip one each time: A, C, E, G, I.", "Easy"),
        ("If A=1, B=2, C=3, what is the sum of the values of the letters in 'CAB'?", ["5", "6", "7", "8"], "B", "3 + 1 + 2 = 6.", "Easy"),
        ("What is the angle between the hands of a clock at 3:00?", ["45 degrees", "60 degrees", "90 degrees", "120 degrees"], "C",
         "At 3:00 the hands are 3 hours apart: 3 x 30 = 90 degrees.", "Medium"),
        ("Today is Monday. What day will it be after 10 days?", ["Wednesday", "Thursday", "Friday", "Saturday"], "B",
         "10 days = 1 week + 3 days. Monday + 3 days = Thursday.", "Medium"),
        ("Find the next number: 1, 4, 9, 16, ?", ["20", "24", "25", "36"], "C", "These are square numbers: 1^2, 2^2, 3^2, 4^2, 5^2 = 25.", "Easy"),
        ("Which is the odd one out: Square, Triangle, Circle, Cube?", ["Square", "Triangle", "Circle", "Cube"], "D",
         "A cube is three-dimensional; the others are flat shapes.", "Easy"),
        ("Doctor : Hospital :: Teacher : ?", ["Student", "School", "Book", "Class"], "B", "A doctor works in a hospital; a teacher works in a school.", "Easy"),
    ],
    ("SSC-CGL", "English Language"): [
        ("Choose the synonym of 'Rapid'.", ["Slow", "Fast", "Weak", "Late"], "B", "Rapid means fast.", "Easy"),
        ("Choose the antonym of 'Ancient'.", ["Old", "Modern", "Historic", "Aged"], "B", "Ancient means very old; modern is its opposite.", "Easy"),
        ("Fill in the blank: She ___ to school every day.", ["go", "goes", "going", "gone"], "B", "A singular subject takes 'goes' in the simple present.", "Easy"),
        ("What is the plural of 'child'?", ["childs", "childes", "children", "childrens"], "C", "'Children' is the irregular plural of child.", "Easy"),
        ("What does the idiom 'a piece of cake' mean?", ["Very easy", "Very costly", "Very tasty", "Very small"], "A", "It means something is very easy to do.", "Easy"),
        ("Choose the correctly spelt word.", ["Neccessary", "Necessary", "Necesary", "Neccesary"], "B", "The correct spelling is 'necessary'.", "Medium"),
        ("What is the past tense of 'write'?", ["writed", "written", "wrote", "writes"], "C", "'Wrote' is the simple past; 'written' is the past participle.", "Easy"),
        ("One word for 'a person who writes books':", ["Editor", "Author", "Reader", "Publisher"], "B", "An author writes books.", "Easy"),
        ("Fill in the blank: He is good ___ mathematics.", ["in", "at", "on", "with"], "B", "'Good at' is the correct collocation.", "Medium"),
        ("Fill in the blank: She is ___ honest woman.", ["a", "an", "the", "no article"], "B", "'Honest' starts with a vowel sound, so 'an' is used.", "Medium"),
    ],
    ("RRB-NTPC", "Mathematics"): [
        ("What is 25% of 80?", ["15", "20", "25", "30"], "B", "25/100 x 80 = 20.", "Easy"),
        ("What is 144 divided by 12?", ["10", "11", "12", "14"], "C", "12 x 12 = 144.", "Easy"),
        ("What is the perimeter of a square with side 9 cm?", ["27 cm", "36 cm", "45 cm", "81 cm"], "B", "Perimeter = 4 x side = 36 cm.", "Easy"),
        ("What is the HCF of 24 and 36?", ["6", "8", "12", "24"], "C", "24 = 2^3 x 3 and 36 = 2^2 x 3^2, so HCF = 2^2 x 3 = 12.", "Medium"),
        ("2/5 expressed as a percentage is:", ["20%", "25%", "40%", "50%"], "C", "2/5 x 100 = 40%.", "Easy"),
        ("Convert 72 km/h into m/s.", ["15 m/s", "18 m/s", "20 m/s", "25 m/s"], "C", "72 x 5/18 = 20 m/s.", "Medium"),
        ("What is the sum of the angles of a triangle?", ["90 degrees", "180 degrees", "270 degrees", "360 degrees"], "B", "The angles of any triangle add up to 180 degrees.", "Easy"),
        ("What is 0.5 x 0.4?", ["0.02", "0.2", "2", "0.9"], "B", "5 x 4 = 20, with two decimal places gives 0.20 = 0.2.", "Medium"),
        ("5 men can finish a job in 10 days. How many days will 10 men take?", ["2 days", "5 days", "10 days", "20 days"], "B",
         "Total work = 50 man-days; 50/10 = 5 days.", "Medium"),
        ("What is the square of 15?", ["205", "215", "225", "235"], "C", "15 x 15 = 225.", "Easy"),
    ],
    ("RRB-NTPC", "General Awareness"): [
        ("In which year did the first passenger train run in India?", ["1825", "1853", "1875", "1900"], "B",
         "The first passenger train ran from Bombay to Thane in 1853.", "Medium"),
        ("Where is the Railway Board headquartered?", ["Mumbai", "Kolkata", "New Delhi", "Chennai"], "C",
         "The Railway Board works from Rail Bhawan, New Delhi.", "Easy"),
        ("What is the chemical symbol of gold?", ["Ag", "Au", "Gd", "Go"], "B", "Au comes from the Latin word 'aurum'.", "Easy"),
        ("Who invented the telephone?", ["Thomas Edison", "Alexander Graham Bell", "Nikola Tesla", "Marconi"], "B",
         "Alexander Graham Bell is credited with inventing the telephone.", "Easy"),
        ("Which planet is known as the Red Planet?", ["Venus", "Mars", "Mercury", "Saturn"], "B", "Mars looks red due to iron oxide on its surface.", "Easy"),
        ("What is the national bird of India?", ["Sparrow", "Peacock", "Parrot", "Eagle"], "B", "The Indian peacock is the national bird.", "Easy"),
        ("Which is the hardest natural substance?", ["Gold", "Iron", "Diamond", "Quartz"], "C", "Diamond is the hardest naturally occurring material.", "Easy"),
        ("What is the currency of Japan?", ["Won", "Yuan", "Yen", "Ringgit"], "C", "Japan uses the yen.", "Easy"),
        ("Which organ pumps blood through the human body?", ["Lungs", "Liver", "Heart", "Kidney"], "C", "The heart pumps blood.", "Easy"),
        ("In which state was Mahatma Gandhi born?", ["Maharashtra", "Gujarat", "Rajasthan", "Uttar Pradesh"], "B", "Gandhi was born in Porbandar, Gujarat.", "Easy"),
    ],
    ("APPSC-G2", "General Studies"): [
        ("Which river is also known as 'Dakshina Ganga'?", ["Krishna", "Godavari", "Penna", "Tungabhadra"], "B", "The Godavari is called Dakshina Ganga (Ganga of the South).", "Medium"),
        ("In which year was the state of Andhra formed as a separate linguistic state from Madras State?", ["1947", "1950", "1953", "1956"], "C", "Andhra State was formed on 1 October 1953.", "Medium"),
        ("Which new state was formed out of Andhra Pradesh on 2 June 2014?", ["Karnataka", "Telangana", "Odisha", "Chhattisgarh"], "B", "Telangana was carved out of Andhra Pradesh in 2014.", "Easy"),
        ("Which of these major ports is located in Andhra Pradesh?", ["Kandla", "Paradip", "Visakhapatnam", "Kochi"], "C", "Visakhapatnam is a major port on the Andhra Pradesh coast.", "Easy"),
        ("The Tirumala Venkateswara temple is located in which district?", ["Guntur", "Tirupati", "Kurnool", "Kadapa"], "B", "Tirumala is in Tirupati district.", "Medium"),
        ("Who is popularly known as 'Andhra Kesari'?", ["Potti Sriramulu", "Tanguturi Prakasam", "Alluri Sitarama Raju", "Gurajada Apparao"], "B", "Tanguturi Prakasam Pantulu is known as Andhra Kesari.", "Medium"),
        ("How many Fundamental Rights are currently guaranteed by the Indian Constitution?", ["Five", "Six", "Seven", "Eight"], "B", "There are six Fundamental Rights since the Right to Property was removed in 1978.", "Medium"),
        ("Who is the constitutional head of a state government in India?", ["Chief Minister", "Governor", "Chief Justice", "Speaker"], "B", "The Governor is the constitutional head of a state.", "Easy"),
        ("Kuchipudi classical dance originated in which state?", ["Kerala", "Tamil Nadu", "Andhra Pradesh", "Odisha"], "C", "Kuchipudi is named after a village in Andhra Pradesh.", "Easy"),
        ("Kolleru Lake lies between the deltas of which two rivers?", ["Krishna and Godavari", "Godavari and Mahanadi", "Krishna and Penna", "Penna and Cauvery"], "A", "Kolleru Lake is between the Krishna and Godavari deltas.", "Hard"),
    ],
    ("UPSC-CSE", "Indian Polity"): [
        ("On which date did the Constitution of India come into force?", ["15 August 1947", "26 November 1949", "26 January 1950", "2 October 1950"], "C", "It came into force on 26 January 1950 (celebrated as Republic Day).", "Easy"),
        ("Who was the Chairman of the Drafting Committee of the Constitution?", ["Jawaharlal Nehru", "Dr. B. R. Ambedkar", "Sardar Patel", "Dr. Rajendra Prasad"], "B", "Dr. B. R. Ambedkar chaired the Drafting Committee.", "Easy"),
        ("The Directive Principles of State Policy are contained in which Part of the Constitution?", ["Part II", "Part III", "Part IV", "Part V"], "C", "Part IV (Articles 36-51) contains the Directive Principles.", "Medium"),
        ("What is the minimum age to be elected as President of India?", ["25 years", "30 years", "35 years", "40 years"], "C", "A candidate must be at least 35 years old.", "Easy"),
        ("What is the maximum strength of the Rajya Sabha?", ["238", "245", "250", "275"], "C", "The maximum strength is 250 (238 elected and 12 nominated).", "Medium"),
        ("Which words were added to the Preamble by the 42nd Amendment?", ["Sovereign, Republic", "Socialist, Secular, Integrity", "Democratic, Justice", "Liberty, Equality"], "B", "The 42nd Amendment (1976) added 'Socialist', 'Secular' and 'Integrity'.", "Medium"),
        ("Who appoints the Governor of a state?", ["Chief Minister", "Prime Minister", "President", "Chief Justice of India"], "C", "The President appoints the Governor.", "Easy"),
        ("Article 32 of the Constitution deals with:", ["Right to Equality", "Right to Constitutional Remedies", "Freedom of Religion", "Right to Education"], "B", "Article 32 lets citizens approach the Supreme Court to enforce fundamental rights.", "Medium"),
        ("What is the normal term of the Lok Sabha?", ["4 years", "5 years", "6 years", "7 years"], "B", "The Lok Sabha's term is 5 years unless dissolved earlier.", "Easy"),
        ("Who is the ex-officio Chairman of the Rajya Sabha?", ["Prime Minister", "President", "Vice-President", "Speaker"], "C", "The Vice-President of India is the ex-officio Chairman.", "Easy"),
    ],
}

# Mock tests: (exam_code, subject, duration_minutes)
MOCK_TESTS = [
    ("SSC-CGL", "General Awareness", 10),
    ("SSC-CGL", "Quantitative Aptitude", 12),
    ("SSC-CGL", "General Intelligence & Reasoning", 10),
    ("SSC-CGL", "English Language", 10),
    ("RRB-NTPC", "Mathematics", 12),
    ("RRB-NTPC", "General Awareness", 10),
    ("APPSC-G2", "General Studies", 12),
    ("UPSC-CSE", "Indian Polity", 12),
]

# Demo student (NOT an admin). Password is for local demonstration only.
DEMO_USER = {
    "full_name": "Demo Student", "email": "demo@example.com", "password": "Demo@1234",
    "date_of_birth": "2002-05-15", "highest_qualification": "Graduate (Bachelor's Degree)",
    "state": "Andhra Pradesh", "district": "Guntur", "preferred_category": "SSC",
}


# ====================================================================
# Insert functions
# ====================================================================
def seed_exams(conn):
    for (name, code, cat, body, level, desc, pattern, syllabus, url) in EXAMS:
        execute_db(
            """INSERT OR IGNORE INTO exams
               (name, short_code, category, conducting_body, govt_level, description,
                exam_pattern, syllabus_summary, official_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, code, cat, body, level, desc, pattern, syllabus, url), conn=conn, commit=False)
    conn.commit()


def exam_id_for(code, conn):
    return query_db("SELECT id FROM exams WHERE short_code = ?", (code,), one=True, conn=conn)["id"]


def subject_id_for(code, subject_name, conn):
    return query_db(
        """SELECT s.id FROM subjects s JOIN exams e ON e.id = s.exam_id
           WHERE e.short_code = ? AND s.name = ?""", (code, subject_name), one=True, conn=conn)["id"]


def seed_subjects(conn):
    for code, subject_list in SUBJECTS.items():
        exam_id = exam_id_for(code, conn)
        for name, desc in subject_list:
            execute_db("INSERT OR IGNORE INTO subjects (exam_id, name, description) VALUES (?, ?, ?)",
                       (exam_id, name, desc), conn=conn, commit=False)
    conn.commit()


def seed_jobs(conn):
    added = 0
    for (title, org, govt, cat, qual, level, min_age, max_age, state, vac,
         start_off, deadline_off, salary, exam_codes, link_key) in JOBS:
        exists = query_db("SELECT id FROM jobs WHERE title = ? AND organization = ?",
                          (title, org), one=True, conn=conn)
        if exists:
            continue
        first_exam = query_db("SELECT * FROM exams WHERE short_code = ?", (exam_codes[0],), one=True, conn=conn)
        link = LINKS[link_key]
        description = (f"DEMONSTRATION RECORD for the post '{title}'. It is sample data created for a college "
                       f"project and is not an official notification.")
        eligibility = (f"Qualification: {qual}. Age: {min_age} to {max_age} years (sample general limits). "
                       f"Age relaxation, nationality, physical standards and other conditions must be checked "
                       f"in the official notification.")
        job_id = execute_db(
            """INSERT INTO jobs
               (title, organization, govt_category, exam_category, required_qualification,
                min_qualification_level, min_age, max_age, state_requirement, vacancies, vacancies_note,
                application_start, application_deadline, salary, description, eligibility_text,
                syllabus_pattern, notification_url, apply_url, age_relaxation_verified, is_demo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1)""",
            (title, org, govt, cat, qual, level, min_age, max_age, state, vac,
             "Sample figure for demonstration, not official", day(start_off), day(deadline_off), salary,
             description, eligibility, first_exam["exam_pattern"], link, link),
            conn=conn, commit=False)
        for code in exam_codes:
            execute_db("INSERT OR IGNORE INTO job_exams (job_id, exam_id) VALUES (?, ?)",
                       (job_id, exam_id_for(code, conn)), conn=conn, commit=False)
        added += 1
    conn.commit()
    return added


def seed_resources(conn):
    for title, url, desc, kind, code in OFFICIAL_RESOURCES:
        exists = query_db("SELECT id FROM official_resources WHERE url = ?", (url,), one=True, conn=conn)
        if exists:
            continue
        exam_id = exam_id_for(code, conn) if code else None
        execute_db(
            """INSERT INTO official_resources (title, url, description, resource_kind, exam_id, last_verified)
               VALUES (?, ?, ?, ?, ?, NULL)""", (title, url, desc, kind, exam_id), conn=conn, commit=False)
    for code, title, year, url, official in PREVIOUS_PAPERS:
        exam_id = exam_id_for(code, conn)
        if query_db("SELECT id FROM previous_papers WHERE exam_id = ? AND title = ?",
                    (exam_id, title), one=True, conn=conn):
            continue
        execute_db("INSERT INTO previous_papers (exam_id, title, year, url, is_official) VALUES (?, ?, ?, ?, ?)",
                   (exam_id, title, year, url, official), conn=conn, commit=False)
    for code, subject, title, desc, rtype, url, official in STUDY_MATERIALS:
        subject_id = subject_id_for(code, subject, conn)
        if query_db("SELECT id FROM study_materials WHERE subject_id = ? AND title = ?",
                    (subject_id, title), one=True, conn=conn):
            continue
        execute_db(
            """INSERT INTO study_materials (subject_id, title, description, resource_type, url, is_official)
               VALUES (?, ?, ?, ?, ?, ?)""", (subject_id, title, desc, rtype, url, official),
            conn=conn, commit=False)
    conn.commit()


def seed_questions_and_tests(conn):
    added = 0
    for (code, subject), items in QUESTIONS.items():
        subject_id = subject_id_for(code, subject, conn)
        for text, options, correct, explanation, difficulty in items:
            if query_db("SELECT id FROM questions WHERE subject_id = ? AND question_text = ?",
                        (subject_id, text), one=True, conn=conn):
                continue
            execute_db(
                """INSERT INTO questions
                   (subject_id, question_text, option_a, option_b, option_c, option_d,
                    correct_option, explanation, difficulty, is_demo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (subject_id, text, options[0], options[1], options[2], options[3],
                 correct, explanation, difficulty), conn=conn, commit=False)
            added += 1
    for code, subject, minutes in MOCK_TESTS:
        exam_id = exam_id_for(code, conn)
        subject_id = subject_id_for(code, subject, conn)
        title = f"{code} - {subject} Practice Test"
        execute_db(
            """INSERT OR IGNORE INTO mock_tests (title, exam_id, subject_id, duration_minutes, num_questions)
               VALUES (?, ?, ?, ?, 10)""", (title, exam_id, subject_id, minutes), conn=conn, commit=False)
    conn.commit()
    return added


def seed_demo_user(conn):
    if query_db("SELECT id FROM users WHERE email = ?", (DEMO_USER["email"],), one=True, conn=conn):
        return False
    execute_db(
        """INSERT INTO users (full_name, email, password_hash, date_of_birth, highest_qualification,
                              state, district, preferred_category, role)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'user')""",
        (DEMO_USER["full_name"], DEMO_USER["email"], generate_password_hash(DEMO_USER["password"]),
         DEMO_USER["date_of_birth"], DEMO_USER["highest_qualification"], DEMO_USER["state"],
         DEMO_USER["district"], DEMO_USER["preferred_category"]), conn=conn)
    return True


def main():
    reset = "--reset" in sys.argv
    with standalone_db() as conn:
        init_db(conn, reset=reset)
        seed_exams(conn)
        seed_subjects(conn)
        jobs_added = seed_jobs(conn)
        seed_resources(conn)
        questions_added = seed_questions_and_tests(conn)
        demo_created = False
    print("Database ready.")
    print(f"  Jobs added: {jobs_added}")
    print(f"  Questions added: {questions_added}")
    print("  Demo student created: " + ("yes (demo@example.com)" if demo_created else "already existed"))
    print("Next: create an admin with  python create_admin.py  (available in Part 9).")


if __name__ == "__main__":
    main()