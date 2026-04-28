import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const outputDir = path.join(repoRoot, "templates");

function setSheetFrame(sheet) {
  sheet.showGridLines = true;
  sheet.freezePanes.freezeRows = 1;
}

function styleTitle(range) {
  range.format.fill.color = "#0f766e";
  range.format.font.bold = true;
  range.format.font.color = "#ffffff";
  range.format.font.size = 12;
}

function styleHeader(range) {
  range.format.fill.color = "#dbeafe";
  range.format.font.bold = true;
  range.format.borders.bottom.style = "thin";
}

function styleNote(range) {
  range.format.fill.color = "#f8fafc";
  range.format.font.color = "#334155";
  range.format.wrapText = true;
}

function styleExample(range) {
  range.format.fill.color = "#fefce8";
}

function setColumnWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, 1, 1).format.columnWidthPx = width;
  });
}

function addManagerTemplateSheet(workbook) {
  const sheet = workbook.worksheets.add("Менеджер");
  setSheetFrame(sheet);

  sheet.getRange("A1:H1").values = [[
    "article",
    "name",
    "quantity",
    "supplier_site",
    "supplier_article",
    "product_url",
    "image_urls_raw",
    "notes",
  ]];
  styleTitle(sheet.getRange("A1:H1"));

  sheet.getRange("A2:H4").values = [
    [
      "TSR-10025",
      "Кроссовки беговые мужские",
      24,
      "supplier-brand.ru",
      "AB-4451",
      "https://supplier-brand.ru/catalog/ab-4451",
      "https://cdn.supplier-brand.ru/ab-4451-1.jpg;https://cdn.supplier-brand.ru/ab-4451-2.jpg",
      "Для Спортмастера прямые ссылки лучше давать через ; без пробелов",
    ],
    ["TSR-10026", "Рюкзак городской 20 л", 12, "supplier-brand.ru", "BP-220", "", "", "Тогда сервис попробует поиск по сайту и интернету"],
    ["", "", "", "", "", "", "", ""],
  ];
  styleExample(sheet.getRange("A2:H3"));

  setColumnWidths(sheet, [130, 260, 90, 180, 150, 320, 420, 220]);
  sheet.getRange("A1:H20").format.wrapText = true;
}

function addClientTemplateSheet(workbook) {
  const sheet = workbook.worksheets.add("Клиент");
  setSheetFrame(sheet);

  sheet.getRange("A1:B1").values = [["article", "client_code"]];
  styleTitle(sheet.getRange("A1:B1"));

  sheet.getRange("A2:B4").values = [
    ["TSR-10025", "SM-RED-42"],
    ["TSR-10026", "4607000012345"],
    ["", ""],
  ];
  styleExample(sheet.getRange("A2:B3"));

  setColumnWidths(sheet, [180, 220]);
  sheet.getRange("A1:B20").format.wrapText = true;
}

function addSportmasterTemplateSheet(workbook) {
  const sheet = workbook.worksheets.add("Спортмастер");
  setSheetFrame(sheet);

  sheet.getRange("A1:B1").values = [["article", "Код цветомодели"]];
  styleTitle(sheet.getRange("A1:B1"));

  sheet.getRange("A2:B4").values = [
    ["TSR-10025", "SM-RED-42"],
    ["TSR-10026", "SM-BLACK-43"],
    ["", ""],
  ];
  styleExample(sheet.getRange("A2:B3"));

  setColumnWidths(sheet, [180, 240]);
  sheet.getRange("A1:B20").format.wrapText = true;
}

function addSportmasterReadmeSheet(workbook) {
  const sheet = workbook.worksheets.add("Как загружать");
  sheet.getRange("A1:C1").values = [["Шаблон для Спортмастера", null, null]];
  sheet.getRange("A1:C1").merge();
  styleTitle(sheet.getRange("A1:C1"));
  sheet.getRange("A3:C11").values = [
    ["Пункт", "Что делать", "Комментарий"],
    ["1", "На листе Спортмастер заполнить article и Код цветомодели", "Каждая строка = один товар в UpdatPic"],
    ["2", "Загрузить этот файл в раздел Клиенты и выбрать клиента Спортмастер", "Сервис упакует фото в ZIP"],
    ["3", "После сборки архива имена файлов будут вида КодЦветомодели_1, КодЦветомодели_2 и т.д.", "Пример: SM-RED-42_1.jpg"],
    ["Формат", "Допустимые файлы: jpg, jpeg, png", "Ссылка на фото должна заканчиваться расширением файла"],
    ["Размер", "До 50 МБ на файл", "Содержимое фото всё равно лучше проверить глазами"],
    ["Ссылки", "Если менеджер даёт прямые ссылки, указывайте каждую отдельно через ; без пробелов", "Порядок ссылок = порядок фото в карточке"],
    ["Важно", "Код цветомодели даёт менеджер", "Без него файлы нельзя правильно назвать для Спортмастера"],
    ["Важно", "На фото не должно быть водяных знаков, ссылок и посторонних товаров", "Это уже правило модерации клиента"],
  ];
  styleHeader(sheet.getRange("A3:C3"));
  styleNote(sheet.getRange("A4:C11"));
  sheet.getRange("A1:C11").format.wrapText = true;
  setColumnWidths(sheet, [90, 360, 320]);
}

function addDetmirTemplateSheet(workbook) {
  const sheet = workbook.worksheets.add("Детский Мир");
  setSheetFrame(sheet);

  sheet.getRange("A1:B1").values = [["article", "Штрихкод товара"]];
  styleTitle(sheet.getRange("A1:B1"));

  sheet.getRange("A2:B4").values = [
    ["TSR-10025", "4607000012345"],
    ["TSR-10026", "4607000012346"],
    ["", ""],
  ];
  styleExample(sheet.getRange("A2:B3"));

  setColumnWidths(sheet, [180, 240]);
  sheet.getRange("A1:B20").format.wrapText = true;
}

function addDetmirReadmeSheet(workbook) {
  const sheet = workbook.worksheets.add("Как загружать");
  sheet.getRange("A1:C1").values = [["Шаблон для Детского Мира", null, null]];
  sheet.getRange("A1:C1").merge();
  styleTitle(sheet.getRange("A1:C1"));
  sheet.getRange("A3:C10").values = [
    ["Пункт", "Что делать", "Комментарий"],
    ["1", "На листе Детский Мир заполнить article и Штрихкод товара", "Каждая строка = один товар в UpdatPic"],
    ["2", "Загрузить этот файл в раздел Клиенты и выбрать клиента Детский Мир", "Сервис упакует фото в ZIP"],
    ["3", "После сборки архива имена файлов будут вида Штрихкод_01, Штрихкод_02 и т.д.", "Пример: 4607000012345_01.jpg"],
    ["Формат", "Допустимые файлы: jpg, jpeg, png, webp", "UpdatPic сохранит подходящее расширение"],
    ["Размер", "Длинная сторона 1000-8000 px, до 1 МБ", "Сервис уменьшит слишком большие изображения"],
    ["Важно", "Штрихкод товара даёт менеджер", "Без него файлы нельзя правильно назвать для Детского Мира"],
    ["Важно", "Фото не должны быть перегружены, с водяными знаками, QR и посторонними логотипами", "Это уже правило модерации клиента"],
  ];
  styleHeader(sheet.getRange("A3:C3"));
  styleNote(sheet.getRange("A4:C10"));
  sheet.getRange("A1:C10").format.wrapText = true;
  setColumnWidths(sheet, [90, 360, 320]);
}

function addReadmeSheet(workbook) {
  const sheet = workbook.worksheets.add("Как использовать");
  sheet.getRange("A1:C1").values = [["UpdatPic templates", null, null]];
  sheet.getRange("A1:C1").merge();
  styleTitle(sheet.getRange("A1:C1"));
  sheet.getRange("A3:C10").values = [
    ["Шаг", "Что делать", "Результат"],
    ["1", "На листе Менеджер заполнить строки под заголовками из первой строки", "Файл можно сразу загружать в раздел Каталог фото"],
    ["2", "Проверить, что у нужных товаров появились фото в локальном каталоге", "Товары будут готовы к клиентской упаковке"],
    ["3", "На листе Клиент заполнить article и client_code и загрузить файл в раздел Клиенты", "Сервис соберёт ZIP-архив под правила клиента"],
    ["4", "Скачать архив и при необходимости проверить несколько файлов глазами", "Можно передавать архив менеджеру или клиенту"],
    ["Поля менеджера", "article и name обязательны; quantity, supplier_site, supplier_article, product_url, image_urls_raw, notes опциональны", "Прямые ссылки на фото указывайте через ;"],
    ["Поля клиента", "client_code это код цветомодели, штрихкод или другой код клиента", "Для разных клиентов можно использовать отдельные файлы сопоставления"],
    ["Важно", "Автопоиск не гарантирует прохождение модерации маркетплейса", "Нужна ручная проверка качества и контента фото"],
  ];
  styleHeader(sheet.getRange("A3:C3"));
  styleNote(sheet.getRange("A4:C10"));
  sheet.getRange("A1:C10").format.wrapText = true;
  setColumnWidths(sheet, [80, 360, 320]);
}

function addSportmasterLinksTemplateSheet(workbook) {
  const sheet = workbook.worksheets.add("Ссылки Спортмастер");
  setSheetFrame(sheet);

  sheet.getRange("A1:B1").values = [["Код цветомодели", "Ссылки на фото"]];
  styleTitle(sheet.getRange("A1:B1"));

  sheet.getRange("A2:B4").values = [
    [
      "SM-RED-42",
      "https://ltdfoto.ru/images/2024/01/17/120140FLA-WH221_1.jpg;https://ltdfoto.ru/images/2024/01/17/120140FLA-WH221_2.jpg",
    ],
    [
      "SM-BLACK-43",
      "https://ltdfoto.ru/images/2024/01/17/120140FLA-WH221_3.jpg",
    ],
    ["", ""],
  ];
  styleExample(sheet.getRange("A2:B3"));
  setColumnWidths(sheet, [220, 760]);
  sheet.getRange("A1:B20").format.wrapText = true;
}

function addSportmasterLinksReadmeSheet(workbook) {
  const sheet = workbook.worksheets.add("Как собрать файл");
  sheet.getRange("A1:C1").values = [["Готовые ссылки для Спортмастера", null, null]];
  sheet.getRange("A1:C1").merge();
  styleTitle(sheet.getRange("A1:C1"));
  sheet.getRange("A3:C10").values = [
    ["Пункт", "Что делать", "Комментарий"],
    ["1", "Заполнить Код цветомодели и Ссылки на фото", "Парсинг и скачивание не нужны"],
    ["2", "Вставлять только прямые открытые ссылки на jpg/jpeg/png", "Ссылка должна заканчиваться расширением"],
    ["3", "Если фото несколько, вставлять ссылки через ; без пробелов", "Порядок ссылок = порядок отображения фото"],
    ["4", "Загрузить файл в блок Готовые ссылки без парсинга", "Сервис соберёт итоговый Excel под Спортмастер"],
    ["Важно", "Ссылки Яндекс Диска для Спортмастера не подходят", "Они обычно не содержат расширение файла"],
    ["Важно", "Если ссылка не прямая, сервис оставит предупреждение в отчёте", "Лучше сразу давать готовые URL на файл"],
    ["Пример", "https://ltdfoto.ru/images/2024/01/17/120140FLA-WH221_4.jpg", "Корректная прямая ссылка"],
  ];
  styleHeader(sheet.getRange("A3:C3"));
  styleNote(sheet.getRange("A4:C10"));
  sheet.getRange("A1:C10").format.wrapText = true;
  setColumnWidths(sheet, [90, 360, 320]);
}

function addDetmirLinksTemplateSheet(workbook) {
  const sheet = workbook.worksheets.add("Ссылки Детский Мир");
  setSheetFrame(sheet);

  sheet.getRange("A1:B1").values = [["Штрихкод товара", "Ссылки на фото"]];
  styleTitle(sheet.getRange("A1:B1"));

  sheet.getRange("A2:B4").values = [
    [
      "4607000012345",
      "https://static.detmir.st/media_out/523/698/3698523/1500/0.jpg\nhttps://static.detmir.st/media_out/523/698/3698523/1500/1.jpg",
    ],
    [
      "4607000012346",
      "https://disk.yandex.ru/d/example-public-link",
    ],
    ["", ""],
  ];
  styleExample(sheet.getRange("A2:B3"));
  setColumnWidths(sheet, [220, 760]);
  sheet.getRange("A1:B20").format.wrapText = true;
}

function addDetmirLinksReadmeSheet(workbook) {
  const sheet = workbook.worksheets.add("Как собрать файл");
  sheet.getRange("A1:C1").values = [["Готовые ссылки для Детского Мира", null, null]];
  sheet.getRange("A1:C1").merge();
  styleTitle(sheet.getRange("A1:C1"));
  sheet.getRange("A3:C10").values = [
    ["Пункт", "Что делать", "Комментарий"],
    ["1", "Заполнить Штрихкод товара и Ссылки на фото", "Парсинг и скачивание не нужны"],
    ["2", "Можно вставлять прямые ссылки на изображения или публичные ссылки Яндекс Диска", "Несколько ссылок допускаются"],
    ["3", "Разделители: перевод строки, пробел, запятая или ;", "Сервис соберёт единый Excel-файл"],
    ["4", "Загрузить файл в блок Готовые ссылки без парсинга", "Сервис соберёт итоговый Excel под Детский Мир"],
    ["Ограничение", "Максимум 30 изображений на товар", "Лишние будут отброшены с предупреждением"],
    ["Важно", "Размер каждого файла должен быть до 1 МБ", "Сервис только формирует файл со ссылками, а не пережимает удалённые файлы"],
    ["Пример", "https://static.detmir.st/media_out/523/698/3698523/1500/0.jpg", "Корректная прямая ссылка"],
  ];
  styleHeader(sheet.getRange("A3:C3"));
  styleNote(sheet.getRange("A4:C10"));
  sheet.getRange("A1:C10").format.wrapText = true;
  setColumnWidths(sheet, [90, 360, 320]);
}

await fs.mkdir(outputDir, { recursive: true });

const managerTemplate = Workbook.create();
addManagerTemplateSheet(managerTemplate);
addReadmeSheet(managerTemplate);

const clientTemplate = Workbook.create();
addClientTemplateSheet(clientTemplate);
addReadmeSheet(clientTemplate);

const sportmasterTemplate = Workbook.create();
addSportmasterTemplateSheet(sportmasterTemplate);
addSportmasterReadmeSheet(sportmasterTemplate);

const detmirTemplate = Workbook.create();
addDetmirTemplateSheet(detmirTemplate);
addDetmirReadmeSheet(detmirTemplate);

const sportmasterLinksTemplate = Workbook.create();
addSportmasterLinksTemplateSheet(sportmasterLinksTemplate);
addSportmasterLinksReadmeSheet(sportmasterLinksTemplate);

const detmirLinksTemplate = Workbook.create();
addDetmirLinksTemplateSheet(detmirLinksTemplate);
addDetmirLinksReadmeSheet(detmirLinksTemplate);

const managerFile = await SpreadsheetFile.exportXlsx(managerTemplate);
await managerFile.save(path.join(outputDir, "manager_import_template.xlsx"));

const clientFile = await SpreadsheetFile.exportXlsx(clientTemplate);
await clientFile.save(path.join(outputDir, "client_mapping_template.xlsx"));

const sportmasterFile = await SpreadsheetFile.exportXlsx(sportmasterTemplate);
await sportmasterFile.save(path.join(outputDir, "sportmaster_upload_template.xlsx"));

const detmirFile = await SpreadsheetFile.exportXlsx(detmirTemplate);
await detmirFile.save(path.join(outputDir, "detmir_upload_template.xlsx"));

const sportmasterLinksFile = await SpreadsheetFile.exportXlsx(sportmasterLinksTemplate);
await sportmasterLinksFile.save(path.join(outputDir, "sportmaster_links_template.xlsx"));

const detmirLinksFile = await SpreadsheetFile.exportXlsx(detmirLinksTemplate);
await detmirLinksFile.save(path.join(outputDir, "detmir_links_template.xlsx"));

console.log("Templates exported to", outputDir);
