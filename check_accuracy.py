import tensorflow as tf
import numpy as np
import pickle
from tensorflow.keras.preprocessing.sequence import pad_sequences
from sklearn.metrics import classification_report, accuracy_score

# 1. Load the Trained Brain and Vocabulary
print("🧠 Loading AI Brain...")
model = tf.keras.models.load_model('resume_classifier.h5', compile=False)
with open('tokenizer.pickle', 'rb') as handle:
    tokenizer = pickle.load(handle)

# 2. Provide NEW, Unseen Testing Data (Do not use the training resumes!)
test_resumes = [
    "i have 5 years of experience building responsive websites using react html css and javascript", # Expected: Web Dev
    "my expertise is in training neural networks using tensorflow and pandas for data science",     # Expected: AI/ML
    "managing sql servers nosql databases and optimizing complex database queries",                 # Expected: Database
    "i build user interfaces and frontend web applications for startups",                           # Expected: Web Dev
    "deep learning computer vision and natural language processing researcher"                      # Expected: AI/ML
]

# Labels: 0 = AI/ML, 1 = Database/Backend, 2 = Web Dev
true_labels = np.array([2, 0, 1, 2, 0])
role_names = ["AI/ML Specialist", "Database/Backend Admin", "Web Developer"]

# 3. Process the text so the AI can read it
sequences = tokenizer.texts_to_sequences(test_resumes)
padded_sequences = pad_sequences(sequences, maxlen=20, padding='post')

# 4. Make Predictions
print("🚀 Running AI Predictions...")
predictions = model.predict(padded_sequences)
predicted_labels = np.argmax(predictions, axis=1)

# 5. Calculate and Print the Accuracy Score!
acc = accuracy_score(true_labels, predicted_labels)
print("\n" + "="*40)
print(f"🎯 OVERALL ACCURACY: {round(acc * 100, 2)}%")
print("="*40 + "\n")

print("📊 DETAILED AI REPORT (Precision & Recall):")
print(classification_report(true_labels, predicted_labels, target_names=role_names))