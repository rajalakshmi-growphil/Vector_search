import csv
import random

def generate_products():
    pain_relievers = [
        "Paracetamol 500mg", "Ibuprofen 400mg", "Aspirin 300mg", "Diclofenac Sodium", 
        "Naproxen 250mg", "Tramadol 50mg", "Aceclofenac 100mg", "Codeine Phosphate",
        "Mefenamic Acid", "Ketorolac Tromethamine"
    ]
    
    antibiotics = [
        "Amoxicillin 500mg", "Azithromycin 500mg", "Ciprofloxacin 500mg", "Doxycycline 100mg",
        "Cephalexin 500mg", "Clarithromycin 250mg", "Metronidazole 400mg", "Ofloxacin 200mg",
        "Erythromycin 500mg", "Nitrofurantoin 100mg"
    ]
    
    supplements = [
        "Vitamin C 1000mg", "Vitamin D3 2000IU", "Multivitamin Daily", "Zinc 50mg",
        "Iron Supplement", "Calcium 500mg", "Fish Oil 1000mg", "B-Complex Vitamin",
        "Magnesium Citrate", "Folic Acid 5mg"
    ]
    
    antacids = [
        "Pantoprazole 400mg", "Omeprazole 20mg", "Ranitidine 150mg", "Rabeprazole 20mg",
        "Domperidone 10mg", "Famotidine 20mg", "Gelusil Antacid Liquid", "Digene Tablet",
        "Antacid Gel", "Magnesium Hydroxide"
    ]
    
    skincare_medicine = [
        "Betadine Ointment", "Hydrocortisone Cream", "Clotrimazole Cream", "Diclofenac Gel",
        "Mupirocin Ointment", "Ketoconazole Shampoo", "Aloe Vera Gel Medical Grade", "Moisturizing Cream",
        "Sunscreen SPF 50", "Anti-Fungal Powder"
    ]

    base_medicines = pain_relievers + antibiotics + supplements + antacids + skincare_medicine
    products = []
    
    # Generate 470 products
    for i in range(1, 471):
        base = random.choice(base_medicines)
        dosage = random.choice(["500mg", "250mg", "100mg", "50mg", "10mg", "Daily", "Extra"])
        products.append((i, f"{base} {dosage} Batch {i}"))
    
    # Adding edge cases: Similar names (Important for vector search testing)
    similar_cases = [
        (471, "Amoxicillin 500mg Capsule"),
        (472, "Amoxicillin 500mg Tablet"),
        (473, "Amoxicillin 250mg Tablet"),
        (474, "Paracetamol 500mg Tablet"),
        (475, "Paracetamol 650mg Dolo")
    ]
    products.extend(similar_cases)
    
    # Adding edge cases: Typos (Testing fuzzy/vector capability)
    typo_cases = [
        (476, "Parasetamol 500mg"),      # Typo s instead of c
        (477, "Amoxcillin 500mg"),       # Missing i
        (478, "Ibubrofen 400mg"),        # b instead of p
        (479, "Pantoprazoll 40mg"),      # double l
        (480, "Vittamin C 1000mg")       # double t
    ]
    products.extend(typo_cases)
    
    # Fill remaining to 500
    for i in range(481, 501):
        suffix = random.choice(["Forte", "Plus", "OD", "BD", "TDS"])
        base = random.choice(base_medicines)
        products.append((i, f"{base} {suffix}"))

    # Write to CSV
    with open('products.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['product_id', 'product_name'])
        writer.writerows(products)
    
    print(f"Generated 500 medicine products in products.csv")

if __name__ == "__main__":
    generate_products()
