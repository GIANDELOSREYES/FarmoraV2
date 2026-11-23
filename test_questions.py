# test_questions.py
# Checks which questions Farmora would answer or refuse, without
# calling the language model, so it runs fast.
# Run:  python test_questions.py

from retrieve import choose_context, search_sections

TESTS = [
    # (question, what should happen)
    ("How do I prepare the land for hybrid rice?", "answer"),
    ("How do I make compost at home?", "answer"),
    ("How can I prevent African swine fever?", "answer"),
    ("what is pigery", "answer"),
    ("How do I raise organic chickens?", "answer"),
    ("What is mokusaku and how is it used?", "answer"),
    ("How do I grow strawberry runners?", "answer"),
    ("How do I grow tomatoes?", "answer"),
    ("What are the symptoms of nitrogen deficiency in rice?", "answer"),
    ("How do I raise goats?", "answer"),
    ("what is the best weather to plant mango", "refuse"),
    ("what is bakery", "refuse"),
    ("How do I raise tilapia?", "refuse"),
    ("How do I grow durian?", "refuse"),
    ("How do I take care of a cow?", "refuse"),
    ("Who won the NBA finals?", "refuse"),
    ("Paano magtanim ng kamatis?", "answer"),
    ("Paano mag-alaga ng baboy?", "answer"),
]

results = []

for question, expected in TESTS:
    context, unknown = choose_context(question)
    got = "answer" if len(context) > 0 else "refuse"

    ranked = search_sections(question)
    best = ranked[0][0] if ranked else 0

    results.append((got == expected, best, expected, got, question))

print("\n================ RESULTS ================")
for passed, best, expected, got, question in results:
    label = "PASS" if passed else "FAIL"
    print(f"{label}  score {best:.2f}  expected {expected:6}  got {got:6}  {question}")

total_passed = sum(1 for result in results if result[0])
print(f"\n{total_passed} of {len(results)} passed")