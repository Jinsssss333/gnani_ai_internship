"""Human-authored demo prompts. Only offer languages with a complete prompt set."""
PROMPTS = {
    "en-IN": {
        "form": "For the synthetic home visit form, press 1.",
        "code": "Enter your four digit visit code.",
        "invalid": "That choice or answer was not understood. Please try again.",
        "visit_done": "Did you complete the home visit? Press 1 for yes, 2 for no.",
        "patient_name": "Say the fictional patient's name.",
        "age": "Say the patient's age.",
        "symptoms": "Describe symptoms, including symptoms the patient does not have.",
        "followup_needed": "Is follow-up needed? Press 1 for yes, 2 for no.",
        "followup_date": "Say the follow-up date. Include the day, month and year if possible.",
        "notes": "Say any extra note.",
        "not_done_reason": "Press 1 for house locked, 2 for patient away, 3 for refused, 4 for other.",
        "record": "Speak after this prompt finishes. Press 1 when finished, 2 to repeat the question.",
        "optional": "Press 9 to skip this optional question.",
        "confirm": "Press 1 to confirm and continue, 2 to answer again, 3 to hear it again.",
        "review": "Press 1 to hear the summary, 2 to edit a detail, 3 to submit the confirmed visit.",
        "edit": "Enter the number of the detail to edit.",
        "saved": "Your visit was saved in SunoCare. Thank you. You may hang up.",
        "failed": "The service could not process this answer. Your earlier answers are saved. Please retry.",
        "unavailable": "We could not complete the form. Your partial visit is saved for review. Please hang up and try later.",
        "yes": "Yes", "no": "No", "none": "Skipped", "heard": "Recorded",
        "reported": "Symptoms present", "negated": "Symptoms absent",
    },
    "hi-IN": {
        "form": "काल्पनिक घर भ्रमण फॉर्म के लिए 1 दबाएं।",
        "code": "अपना चार अंकों का विज़िट कोड दर्ज करें।",
        "invalid": "उत्तर समझ नहीं आया। कृपया फिर से कोशिश करें।",
        "visit_done": "क्या घर की मुलाकात पूरी हुई? हाँ के लिए 1, नहीं के लिए 2 दबाएं।",
        "patient_name": "काल्पनिक मरीज़ का नाम बताएं।",
        "age": "मरीज़ की उम्र बताएं।",
        "symptoms": "मरीज़ के लक्षण बताएं। जो लक्षण नहीं हैं, वे भी बताएं।",
        "followup_needed": "क्या अगली मुलाकात ज़रूरी है? हाँ के लिए 1, नहीं के लिए 2 दबाएं।",
        "followup_date": "अगली मुलाकात की तारीख बताएं। संभव हो तो दिन, महीना और साल बताएं।",
        "notes": "कोई अतिरिक्त जानकारी बताएं।",
        "not_done_reason": "घर बंद के लिए 1, मरीज़ बाहर के लिए 2, मना करने के लिए 3, अन्य के लिए 4 दबाएं।",
        "record": "सवाल खत्म होने के बाद बोलें। बोलना खत्म होने पर 1 दबाएं। सवाल फिर सुनने के लिए 2 दबाएं।",
        "optional": "इस वैकल्पिक सवाल को छोड़ने के लिए 9 दबाएं।",
        "confirm": "सही है और आगे बढ़ने के लिए 1, फिर जवाब देने के लिए 2, फिर सुनने के लिए 3 दबाएं।",
        "review": "सभी जवाब सुनने के लिए 1, सुधारने के लिए 2, पुष्टि किए हुए फॉर्म को जमा करने के लिए 3 दबाएं।",
        "edit": "जिस जानकारी को सुधारना है उसका नंबर दबाएं।",
        "saved": "आपकी मुलाकात सुनोकेयर में सेव हो गई है। धन्यवाद। अब कॉल बंद कर सकते हैं।",
        "failed": "अभी जवाब प्रोसेस नहीं हुआ। पिछले जवाब सेव हैं। कृपया फिर कोशिश करें।",
        "unavailable": "फॉर्म पूरा नहीं हुआ। अधूरी मुलाकात सेव है। कृपया कॉल बंद करके बाद में कोशिश करें।",
        "yes": "हाँ", "no": "नहीं", "none": "छोड़ा गया", "heard": "दर्ज किया गया",
        "reported": "मौजूद लक्षण", "negated": "जो लक्षण नहीं हैं",
    },
}
LANGUAGE_MENU = [("hi-IN", "सुनोकेयर में स्वागत है। हिंदी के लिए 2 दबाएं।"),
                 ("en-IN", "Welcome to SunoCare. For English, press 4. Synthetic data only.")]

PROMPTS['en-IN'].update({
    'review': 'Press 1 to review each field, 2 to edit, 3 to finish, or 9 to save a draft.',
    'review_keys': 'Press 1 for next, 2 to edit this field, 3 to repeat, or 9 to finish reviewing.',
    'submit_menu': 'Press 1 to submit, 2 to review again, or 9 to save as draft.',
    'keypad_option': 'Press 4 to enter digits instead, or 0 to save a draft.',
    'date_keypad': 'Enter eight digits: day, month, four digit year. Press star to clear.',
    'age_keypad': 'Enter age in digits, then hash. Press star to clear.',
    'fixed_field': 'This visit outcome cannot be changed here. Press 1 for next or 9 to finish.',
    'unavailable': 'Your draft is saved in SunoCare under Needs review. It has not been submitted. You may hang up.',
})
PROMPTS['hi-IN'].update({
    'review': 'हर जवाब जाँचने के लिए 1, सुधारने के लिए 2, समाप्त करने के लिए 3, अधूरा फॉर्म सेव करने के लिए 9 दबाएं।',
    'review_keys': 'अगले जवाब के लिए 1, सुधारने के लिए 2, फिर सुनने के लिए 3, समीक्षा समाप्त करने के लिए 9 दबाएं।',
    'submit_menu': 'जमा करने के लिए 1, फिर जाँचने के लिए 2, अधूरा फॉर्म सेव करने के लिए 9 दबाएं।',
    'keypad_option': 'अंक दर्ज करने के लिए 4, अधूरा फॉर्म सेव करने के लिए 0 दबाएं।',
    'date_keypad': 'आठ अंक दर्ज करें: दो अंक दिन, दो अंक महीना, चार अंक साल। मिटाने के लिए स्टार दबाएं।',
    'age_keypad': 'उम्र के अंक दर्ज करके हैश दबाएं। मिटाने के लिए स्टार दबाएं।',
    'fixed_field': 'यह जानकारी यहाँ बदल नहीं सकती। आगे के लिए 1, समीक्षा समाप्त करने के लिए 9 दबाएं।',
    'unavailable': 'अधूरा फॉर्म सुनोकेयर में समीक्षा के लिए सेव है। अभी जमा नहीं हुआ है। अब कॉल बंद कर सकते हैं।',
})

for language, labels in {
    'en-IN': ['Visit completed', 'Patient name', 'Age', 'Symptoms', 'Follow-up needed', 'Follow-up date', 'Notes', 'Reason'],
    'hi-IN': ['मुलाकात पूरी हुई', 'मरीज़ का नाम', 'उम्र', 'लक्षण', 'अगली मुलाकात ज़रूरी', 'अगली मुलाकात की तारीख', 'अतिरिक्त जानकारी', 'कारण'],
}.items():
    for field, title in zip(['visit_done', 'patient_name', 'age', 'symptoms', 'followup_needed', 'followup_date', 'notes', 'not_done_reason'], labels):
        PROMPTS[language]['label_' + field] = title
PROMPTS['en-IN']['followup_date'] = 'Say the follow-up date with day, month and year. Press 9 to leave it for supervisor review and continue.'
PROMPTS['hi-IN']['followup_date'] = 'अगली मुलाकात का दिन, महीना और साल बताएं। इसे समीक्षा के लिए छोड़कर आगे बढ़ने के लिए 9 दबाएं।'
