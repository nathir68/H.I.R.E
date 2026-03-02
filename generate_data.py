import csv
import random

# Tech vocabularies for each role
tech_keywords = {
    0: ["python", "machine learning", "tensorflow", "keras", "deep learning", "nlp", "computer vision", "data science", "pandas", "numpy", "pytorch", "scikit-learn", "ai", "neural networks", "data analysis", "predictive modeling"],
    1: ["sql", "postgresql", "mongodb", "mysql", "nodejs", "express", "api", "backend", "database administrator", "nosql", "server", "aws", "docker", "kubernetes", "redis", "caching", "restful api", "system architecture"],
    2: ["html", "css", "javascript", "react", "angular", "vue", "frontend", "responsive design", "ui/ux", "tailwind", "bootstrap", "web developer", "typescript", "figma", "sass", "web performance", "dom manipulation"]
}

# Professional filler words
fillers = [
    "highly experienced in", "proven track record working with", "skilled at developing with", 
    "proficient in", "built scalable applications using", "over 5 years of experience in", 
    "deep knowledge of", "specializing in", "focused on engineering solutions with",
    "passionate about", "expert level understanding of", "hands-on experience in"
]

dataset = []

print("🧬 Synthesizing 600 AI Resumes...")
# Create 200 resumes for each category
for role_label, keywords in tech_keywords.items():
    for _ in range(200):
        intro = random.choice(fillers)
        skills = " ".join(random.sample(keywords, random.randint(6, 10)))
        outro = random.choice(fillers)
        more_skills = " ".join(random.sample(keywords, random.randint(3, 5)))
        
        resume_text = f"{intro} {skills}. {outro} {more_skills}."
        dataset.append([resume_text, role_label])

# Shuffle to prevent learning patterns
random.shuffle(dataset)

# Save to CSV
with open('synthetic_resumes.csv', 'w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(["resume_text", "label"]) 
    writer.writerows(dataset)

print("✅ Successfully generated 'synthetic_resumes.csv' with 600 unique records!")