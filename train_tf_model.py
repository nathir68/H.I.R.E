import tensorflow as tf
import numpy as np
import pandas as pd
import pickle
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout, Embedding, GlobalAveragePooling1D
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences

print("📂 Loading the massive synthetic dataset...")
df = pd.read_csv('synthetic_resumes.csv')
resumes = df['resume_text'].astype(str).tolist()
labels = df['label'].values

# Tokenize with larger vocab and length
vocab_size = 2000 
max_length = 30 
tokenizer = Tokenizer(num_words=vocab_size, oov_token="<OOV>")
tokenizer.fit_on_texts(resumes)
sequences = tokenizer.texts_to_sequences(resumes)
padded_sequences = pad_sequences(sequences, maxlen=max_length, padding='post')

with open('tokenizer.pickle', 'wb') as handle:
    pickle.dump(tokenizer, handle, protocol=pickle.HIGHEST_PROTOCOL)

print("🔥 Building the Upgraded Neural Network...")
model = Sequential([
    Embedding(vocab_size, 32, input_length=max_length), 
    GlobalAveragePooling1D(),
    Dense(64, activation='relu'), 
    Dropout(0.3), 
    Dense(32, activation='relu'),
    Dropout(0.3),
    Dense(3, activation='softmax')
])

model.compile(loss='sparse_categorical_crossentropy', optimizer='adam', metrics=['accuracy'])

print("🚀 Training the Model (Aiming for >95%)...")
# validation_split=0.2 means 20% of the 600 resumes (120 resumes) are held back to test TRUE accuracy
history = model.fit(padded_sequences, labels, epochs=40, validation_split=0.2, verbose=1)

model.save('resume_classifier.h5')
print("\n✅ Elite TensorFlow Model Saved Successfully as 'resume_classifier.h5'!")

final_acc = history.history['val_accuracy'][-1]
print(f"🎯 FINAL UNSEEN DATA ACCURACY: {round(final_acc * 100, 2)}%")