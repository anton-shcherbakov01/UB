import hashlib

# === ДАННЫЕ ИЗ ТВОЕГО ЛОГА ===
received_hash_robo = "977603F43CB11D79B140262AD0744040"  # То, что прислала Робокасса
amount = "1490.00"
inv_id = "14"
shp_param = "Shp_user_id=1"

# === ТВОИ ПАРОЛИ (которые ты мне скинул) ===
pass1 = "YYN9vvdzB3S7rq98Ygum"
pass2 = "rpLO6LJOe57biuvx0fN8"

print(f"--- РАССЛЕДОВАНИЕ ИНЦИДЕНТА №14 ---")
print(f"Ищем хэш: {received_hash_robo}\n")

def check(name, string_to_hash):
    calc_hash = hashlib.md5(string_to_hash.encode('utf-8')).hexdigest().upper()
    print(f"[{name}]")
    print(f"Строка: {string_to_hash}")
    print(f"Хэш:    {calc_hash}")
    
    if calc_hash == received_hash_robo:
        print("✅ БИНГО! РОБОКАССА ИСПОЛЬЗОВАЛА ИМЕННО ЭТУ КОМБИНАЦИЮ!")
        return True
    print("❌ Мимо\n")
    return False

# ВАРИАНТ 1: Правильная формула + Пароль #2 (Как должно быть)
s1 = f"{amount}:{inv_id}:{pass2}:{shp_param}"
if check("Вариант 1 (Идеал)", s1):
    print(">>> ВЫВОД: Робокасса использует верный Пароль #2.")
    print(">>> ПОЧЕМУ ОШИБКА? Значит, твой Python-код в контейнере использует СТАРЫЙ пароль.")
    print(">>> РЕШЕНИЕ: Перезапусти контейнер: docker-compose down && docker-compose up -d --build")
    exit()

# ВАРИАНТ 2: Правильная формула + Пароль #1 (Вдруг перепутаны местами)
s2 = f"{amount}:{inv_id}:{pass1}:{shp_param}"
if check("Вариант 2 (Пароль #1 вместо #2)", s2):
    print(">>> ВЫВОД: Робокасса почему-то использовала Пароль #1 для подписи ResultURL.")
    exit()

# ВАРИАНТ 3: Без Shp параметров (Вдруг Робокасса их потеряла)
s3 = f"{amount}:{inv_id}:{pass2}"
check("Вариант 3 (Потерян Shp)", s3)

# ВАРИАНТ 4: Без десятичных знаков (1490 вместо 1490.00)
s4 = f"1490:{inv_id}:{pass2}:{shp_param}"
check("Вариант 4 (Сумма без копеек)", s4)

print("\n--- ИТОГ ---")
print("Если ни один вариант не подошел - значит, пароль на сайте Робокассы")
print("ОТЛИЧАЕТСЯ от того, что ты прописал в скрипте (rpLO6LJOe57biuvx0fN8).")