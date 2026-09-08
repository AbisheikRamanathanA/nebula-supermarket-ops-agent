from db import init_db, upsert_product
init_db()
products = [
    ("Aashirvaad Atta 5kg","packet",240,280,12,5,5,"1101"),
    ("Tata Salt 1kg","kg",18,25,25,5,5,"2501"),
    ("Amul Butter 100g","packet",48,62,10,3,12,"0405"),
    ("Fortune Sunflower Oil 1L","litre",110,135,8,3,5,"1512"),
    ("Maggi 70g","packet",12,14,50,10,12,"1902"),
    ("Sugar","kg",42,48,20,5,0,"1701"),
]
for p in products:
    upsert_product(*p)
print("Seeded demo inventory.")
