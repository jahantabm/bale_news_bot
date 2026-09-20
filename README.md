# Jahantab Bale News Bot

بات مستقل انتشار اخبار برای کانال بله `jahantabnews`.

## قابلیت‌ها

- دریافت اخبار از چند منبع فارسی
- فیلتر موضوعی برای ایران/آمریکا، حزب‌الله لبنان، انصارالله یمن، تنگه هرمز و درگیری‌های منطقه‌ای
- حذف خبرهای تکراری
- خلاصه‌سازی استخراجی بر اساس متن RSS (بدون ساختن اطلاعات جدید)
- تلاش برای پیدا کردن تصویر خبر از RSS یا `og:image`
- ارسال عکس + خلاصه + دکمه «مشاهده خبر»
- اجرای زمان‌بندی‌شده با GitHub Actions

## تنظیمات GitHub

### Secret

در:
`Settings → Secrets and variables → Actions → Secrets`

این Secret را بسازید:

`BALE_BOT_TOKEN`

### Repository Variable

در:
`Settings → Secrets and variables → Actions → Variables`

این Variable را بسازید:

`BALE_CHAT_ID`

مقدار آن باید شناسه کانال/چتی باشد که بات اجازه ارسال در آن دارد.

بات بله را به کانال اضافه کنید و دسترسی لازم برای ارسال پیام/رسانه را بدهید.

## تست

از GitHub:
`Actions → Jahantab Bale News Bot → Run workflow`

اگر موفق باشد، خبرهای مرتبط در کانال منتشر می‌شوند.

## نکته

این پروژه مستقل است و به ربات تلگرام شما (`@jahantab_news`) دست نمی‌زند.
