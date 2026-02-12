import os

# Настройки
source_dir = "."  # текущая папка
output_file = "code_collection.txt"
extensions = ['.py', '.js', '.html', '.css', '.cpp', '.c', '.h', '.java', '.php']
exclude_dirs = ['.git', '__pycache__', 'venv', 'env', 'node_modules', '.idea', '.vscode']
current_script = os.path.basename(__file__)  # имя текущего скрипта

print(f"🔍 Поиск файлов в {os.path.abspath(source_dir)} и всех подпапках...")
print(f"🚫 Исключаем из обработки: {current_script}")
print("-" * 50)

all_code = []
processed_files = 0
skipped_files = 0

for root, dirs, files in os.walk(source_dir):
    # Исключаем ненужные папки
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    
    for file in files:
        file_path = os.path.join(root, file)
        rel_path = os.path.relpath(file_path, source_dir)
        
        # Исключаем сам скрипт
        if file == current_script:
            print(f"⏭️  Пропущен (сам скрипт): {rel_path}")
            skipped_files += 1
            continue
            
        if any(file.endswith(ext) for ext in extensions):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                all_code.append(f"\n{'='*80}\n")
                all_code.append(f"Файл: {rel_path}\n")
                all_code.append(f"Папка: {os.path.dirname(rel_path) or '.'}\n")
                all_code.append(f"{'='*80}\n\n")
                all_code.append(content)
                all_code.append("\n")
                
                processed_files += 1
                print(f"✓ Обработан: {rel_path}")
                
            except UnicodeDecodeError:
                print(f"✗ Ошибка кодировки: {rel_path}")
                skipped_files += 1
            except Exception as e:
                print(f"✗ Ошибка: {rel_path} - {e}")
                skipped_files += 1

# Сохраняем результат
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(f"# СБОРКА КОДА\n")
    f.write(f"# Источник: {os.path.abspath(source_dir)}\n")
    f.write(f"# Обработано файлов: {processed_files}\n")
    f.write(f"# Пропущено файлов: {skipped_files}\n")
    f.write(f"# Дата: {__import__('datetime').datetime.now()}\n")
    f.write(f"{'='*80}\n")
    f.write(''.join(all_code))

print("\n" + "=" * 50)
print(f"✅ ГОТОВО!")
print(f"📊 Обработано файлов: {processed_files}")
print(f("⏭️  Пропущено файлов: {skipped_files}"))
print(f"📁 Результат сохранен в: {output_file}")
print(f"📂 Обработаны все папки и подпапки")