import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const outputDir = path.join(repoRoot, "templates");

function setSheetFrame(sheet) {
  sheet.showGridLines = true;
  sheet.freezePanes.freezeRows = 2;
}

function styleTitle(range) {
  range.format.fill.color = "#0f766e";
  range.format.font.bold = true;
  range.format.font.color = "#ffffff";
  range.format.font.size = 12;
}

function styleInstruction(range) {
  range.format.fill.color = "#f8fafc";
  range.format.font.color = "#334155";
  range.format.wrapText = true;
  range.format.verticalAlignment = "top";
}

function styleHeader(range) {
  range.format.fill.color = "#dbeafe";
  range.format.font.bold = true;
  range.format.wrapText = true;
  range.format.borders.bottom.style = "thin";
}

function styleExample(range) {
  range.format.fill.color = "#fefce8";
  range.format.wrapText = true;
}

function setColumnWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, 1, 1).format.columnWidthPx = width;
  });
}

function addManagerTemplateSheet(workbook) {
  const sheet = workbook.worksheets.add("Менеджер");
  sheet.freezePanes.freezeRows = 1;
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
      "Если прямые фото уже есть, парсер можно не ждать",
    ],
    ["TSR-10026", "Рюкзак городской 20 л", 12, "supplier-brand.ru", "BP-220", "", "", "Тогда сервис попробует поиск по сайту и интернету"],
    ["", "", "", "", "", "", "", ""],
  ];
  styleExample(sheet.getRange("A2:H3"));
  sheet.getRange("A1:H20").format.wrapText = true;
  setColumnWidths(sheet, [130, 260, 90, 180, 150, 320, 420, 220]);
}

function addManagerReadmeSheet(workbook) {
  const sheet = workbook.worksheets.add("Как использовать");
  sheet.getRange("A1:C1").values = [["UpdatPic templates", null, null]];
  sheet.getRange("A1:C1").merge();
  styleTitle(sheet.getRange("A1:C1"));
  sheet.getRange("A3:C9").values = [
    ["Шаг", "Что делать", "Результат"],
    ["1", "На листе Менеджер заполнить article и name", "Файл можно загружать в Каталог фото"],
    ["2", "Если прямые фото уже есть, вставить их в image_urls_raw", "Сервис пойдёт по ним без лишнего поиска"],
    ["3", "Если прямых фото нет, заполнить сайт поставщика или product_url", "Сервис попробует сам найти картинки"],
    ["4", "Проверить локальный каталог и затем перейти в раздел Клиенты", "Дальше фото можно упаковать под площадку"],
    ["Поля", "article и name обязательны; quantity, supplier_site, supplier_article, product_url, image_urls_raw, notes опциональны", "Ссылки на фото можно разделять ; , пробелом или переносом строки"],
    ["Важно", "Поиск из интернета не гарантирует модерацию маркетплейса", "Нужна ручная проверка финального набора"],
  ];
  styleHeader(sheet.getRange("A3:C3"));
  styleInstruction(sheet.getRange("A4:C9"));
  sheet.getRange("A1:C9").format.wrapText = true;
  setColumnWidths(sheet, [90, 380, 320]);
}

function addSportmasterTemplateSheet(workbook) {
  const sheet = workbook.worksheets.add("Спортмастер");
  setSheetFrame(sheet);

  sheet.getRange("A1:D1").values = [[
    "Артикул UpdatPic. Нужен, если фото уже спарсены и лежат в локальном каталоге сервиса.",
    "Код цветомодели производителя. Если значения нет, менеджер составляет его в формате КодМодели-КодЦвета. Допустимые символы: заглавные латинские буквы, цифры, пробел -.#_+.",
    "Источник фото: каталог или ссылки. Если не заполнено, сервис выберет ссылки при наличии URL, иначе каталог.",
    "Для каждого фото указать отдельную ссылку. Заполнять через ; подряд без пробелов. Фото должны лежать на открытом ресурсе, а URL должен заканчиваться на jpeg, jpg или png.",
  ]];
  styleInstruction(sheet.getRange("A1:D1"));

  sheet.getRange("A2:D2").values = [["article", "Код цветомодели*", "Источник фото", "Ссылки на фото"]];
  styleTitle(sheet.getRange("A2:D2"));

  sheet.getRange("A3:D6").values = [
    ["TSR-10025", "143ADELE-BG6", "каталог", ""],
    ["", "143ADELE-PH6", "ссылки", "https://technosite.ru/linkpics/179/179457_2b.jpg;https://technosite.ru/linkpics/179/179457_0.jpg"],
    ["TSR-10027", "143ADELE-PN6", "", ""],
    ["", "", "", ""],
  ];
  styleExample(sheet.getRange("A3:D5"));
  sheet.getRange("A1:D20").format.wrapText = true;
  setColumnWidths(sheet, [200, 300, 160, 760]);
}

function addSportmasterReadmeSheet(workbook) {
  const sheet = workbook.worksheets.add("Как использовать");
  sheet.getRange("A1:C1").values = [["Шаблон Спортмастер", null, null]];
  sheet.getRange("A1:C1").merge();
  styleTitle(sheet.getRange("A1:C1"));
  sheet.getRange("A3:C11").values = [
    ["Сценарий", "Что заполнить", "Что получите"],
    ["А. Фото уже спарсены", "article + Код цветомодели. Ссылки оставить пустыми или написать Источник фото = каталог", "ZIP с файлами КодЦветомодели_1, КодЦветомодели_2 и т.д."],
    ["Б. Готовые ссылки уже есть", "Код цветомодели + Ссылки на фото. Можно article не заполнять и указать Источник фото = ссылки", "Excel со ссылками для загрузки в Спортмастер"],
    ["Правило ссылок", "Каждое фото отдельной ссылкой, через ; без пробелов", "Порядок ссылок = порядок фото в карточке"],
    ["Правило URL", "Только открытые прямые ссылки на jpg/jpeg/png", "Яндекс Диск и поисковые страницы не подходят"],
    ["Важно", "Один и тот же файл можно смешивать: часть строк из каталога, часть по готовым ссылкам", "Сервис отдаст оба результата, если нужны оба"],
    ["Пример имени", "143ADELE-BG6_1.jpg", "Формат финального файла для локального каталога"],
  ];
  styleHeader(sheet.getRange("A3:C3"));
  styleInstruction(sheet.getRange("A4:C11"));
  sheet.getRange("A1:C11").format.wrapText = true;
  setColumnWidths(sheet, [160, 370, 340]);
}

function addDetmirTemplateSheet(workbook) {
  const sheet = workbook.worksheets.add("Детский Мир");
  setSheetFrame(sheet);

  sheet.getRange("A1:D1").values = [[
    "Артикул UpdatPic. Нужен, если фото уже спарсены и лежат в локальном каталоге сервиса.",
    "Штрихкод товара. Если штрихкодов несколько, указывайте целевой код для выгрузки этой строки.",
    "Источник фото: каталог или ссылки. Если не заполнено, сервис выберет ссылки при наличии URL, иначе каталог.",
    "Прямая ссылка на изображение, можно вставить несколько. Поддерживаются прямые URL и публичные ссылки из раздела Файлы Яндекс Диска. Разделители: перевод строки, пробел, запятая или ;",
  ]];
  styleInstruction(sheet.getRange("A1:D1"));

  sheet.getRange("A2:D2").values = [["article", "Штрихкод товара*", "Источник фото", "Ссылки на изображения товара"]];
  styleTitle(sheet.getRange("A2:D2"));

  sheet.getRange("A3:D6").values = [
    ["TSR-10025", "4660120067909", "каталог", ""],
    ["", "4660120067916", "ссылки", "https://static.detmir.st/media_out/523/698/3698523/1500/0.jpg\nhttps://static.detmir.st/media_out/523/698/3698523/1500/1.jpg"],
    ["", "4660120067923", "ссылки", "https://disk.yandex.ru/d/example-public-link"],
    ["", "", "", ""],
  ];
  styleExample(sheet.getRange("A3:D5"));
  sheet.getRange("A1:D20").format.wrapText = true;
  setColumnWidths(sheet, [200, 220, 160, 760]);
}

function addDetmirReadmeSheet(workbook) {
  const sheet = workbook.worksheets.add("Как использовать");
  sheet.getRange("A1:C1").values = [["Шаблон Детский Мир", null, null]];
  sheet.getRange("A1:C1").merge();
  styleTitle(sheet.getRange("A1:C1"));
  sheet.getRange("A3:C12").values = [
    ["Сценарий", "Что заполнить", "Что получите"],
    ["А. Фото уже спарсены", "article + Штрихкод товара. Ссылки оставить пустыми или написать Источник фото = каталог", "ZIP с файлами Штрихкод_01, Штрихкод_02 и т.д."],
    ["Б. Готовые ссылки уже есть", "Штрихкод товара + Ссылки на изображения товара. article можно не заполнять и указать Источник фото = ссылки", "Excel со ссылками для загрузки в Детский Мир"],
    ["Разделители", "Перевод строки, пробел, запятая или ;", "Сервис сам нормализует список"],
    ["Ограничение", "Максимум 30 ссылок на товар", "Лишние будут отброшены с предупреждением"],
    ["Требования", "Формат jpg/png/webp, длинная сторона 1000-8000 px, объём до 1 МБ", "Для удалённых ссылок размеры и вес нужно проверять на стороне источника"],
    ["Важно", "Один и тот же файл можно смешивать: часть строк из каталога, часть по готовым ссылкам", "Сервис отдаст оба результата, если нужны оба"],
    ["Пример имени", "4660120067909_01.jpg", "Формат финального файла для локального каталога"],
  ];
  styleHeader(sheet.getRange("A3:C3"));
  styleInstruction(sheet.getRange("A4:C12"));
  sheet.getRange("A1:C12").format.wrapText = true;
  setColumnWidths(sheet, [160, 390, 330]);
}

await fs.mkdir(outputDir, { recursive: true });

const managerTemplate = Workbook.create();
addManagerTemplateSheet(managerTemplate);
addManagerReadmeSheet(managerTemplate);

const sportmasterTemplate = Workbook.create();
addSportmasterTemplateSheet(sportmasterTemplate);
addSportmasterReadmeSheet(sportmasterTemplate);

const detmirTemplate = Workbook.create();
addDetmirTemplateSheet(detmirTemplate);
addDetmirReadmeSheet(detmirTemplate);

const managerFile = await SpreadsheetFile.exportXlsx(managerTemplate);
await managerFile.save(path.join(outputDir, "manager_import_template.xlsx"));

const sportmasterFile = await SpreadsheetFile.exportXlsx(sportmasterTemplate);
await sportmasterFile.save(path.join(outputDir, "sportmaster_upload_template.xlsx"));

const detmirFile = await SpreadsheetFile.exportXlsx(detmirTemplate);
await detmirFile.save(path.join(outputDir, "detmir_upload_template.xlsx"));

for (const legacyName of [
  "client_mapping_template.xlsx",
  "sportmaster_links_template.xlsx",
  "detmir_links_template.xlsx",
]) {
  await fs.rm(path.join(outputDir, legacyName), { force: true });
}

console.log("Templates exported to", outputDir);
