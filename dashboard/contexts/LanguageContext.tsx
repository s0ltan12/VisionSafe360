
import React, { createContext, useContext, useState } from 'react';

export type Language = 'en' | 'ar';
export type Direction = 'ltr' | 'rtl';

const translations = {
  en: {
    // Nav
    overview: "Home Dashboard",
    liveFeeds: "Live Monitoring",
    alerts: "Alerts",
    incidents: "Incident History",
    ergonomics: "Ergonomics Analysis",
    reports: "Analytics",
    users: "User Management",
    cameras: "Camera Management",
    health: "System Health",
    monitoring: "Safety Monitoring",
    analytics: "Data & Reports",
    system: "System Administration",
    configuration: "Configuration",
    
    // Header
    systemActive: "Edge Server Online",
    systemOffline: "Edge Server Offline",
    systemOptimal: "System Optimal",
    searchPlaceholder: "Search records...",
    logout: "Logout",
    
    // KPIs
    mtta: "MTTA (Avg. Acknowledge)",
    mttr: "MTTR (Avg. Resolve)",
    safetyScore: "Compliance Rate",
    activeAlerts: "Active Alerts",
    lastUpdated: "Last Update",

    // Severity
    high: "High",
    medium: "Medium",
    low: "Low",

    // Ergonomics
    ergonomicExposure: "Postural Risk Exposure",
    rulaScore: "Avg RULA Score",
    riskyDuration: "Risky Posture Duration",
    badPostures: "Bad Postures Detected",
    ergoTrends: "Ergonomic Trends",
    riskByZone: "Risk Distribution by Zone",

    // Health
    edgeNodes: "Edge Computing Nodes",
    nodeStatus: "Node Status",
    latency: "Latency",
    uptime: "Uptime",
    storage: "Storage Health",
    cpuUsage: "CPU Usage",
    
    // Dashboard & Others
    safetyOverview: "Factory Safety Status",
    realTimeMonitoring: "Real-time AI surveillance active.",
    camerasOnline: "Sensors Online",
    incidentTrends: "Safety Trends (Weekly)",
    criticalZones: "High Risk Zones",
    viewAllZones: "View Map",
    liveIncidentFeed: "Recent Activity",
    viewAllEvents: "Full History",
    highRisk: "DANGER",
    processing: "Active",
    allZones: "All Areas",
    
    // Statuses
    new: "New",
    notified: "Notified",
    acknowledged: "Acknowledged",
    resolved: "Resolved",
    dismissed: "Dismissed",
    archived: "Archived",
    active: "Active",
    inactive: "Inactive",
    logged: "Logged",
    investigation: "In Investigation",
    online: "Online",
    offline: "Offline",
    
    // General
    zoneA: "Production A",
    zoneB: "Warehouse B",
    zoneC: "Loading Dock",
    zoneD: "Assembly Line",
    admin: "System Admin",
    safetyengineer: "Safety Engineer",
    dataanalyst: "Data Analyst",
    reportIncident: "Report New Incident",
    exportCSV: "Export Data",
    addUser: "Add User",
    addCamera: "Add Stream",
    cameraName: "Stream Name",
    rtspUrl: "Source URL",
    location: "Zone",
    saveChanges: "Save Configuration",

    // Filters
    allSeverities: "All Severities",
    allTypes: "All Types",
    allStatuses: "All Statuses",
    filter: "Filter",

    // Actions & Messages
    noResults: "No results found.",
    notifications: "Notifications",
    noNotifications: "No new notifications",
    markAllRead: "Mark All Read",
    confirmDelete: "Are you sure you want to delete this item?",
    deleteSuccess: "Deleted successfully!",
    addedSuccessfully: "Added successfully!",
    close: "Close",
    delete: "Delete",
    cancel: "Cancel",
    submit: "Submit",
    acknowledge: "Acknowledge",
    resolve: "Resolve",
    escalate: "Escalate to Incident",

    // Table headers
    id: "ID",
    alertType: "Type",
    severity: "Severity",
    timestamp: "Timestamp",
    status: "Status",
    action: "Action",
    alertDetails: "Alert Details",
    date: "Date",
    category: "Category",
    description: "Description",

    // Configuration
    systemConfiguration: "System Configuration",
    sitesZones: "Sites & Zones",
    policies: "Policies",
    integrations: "Integrations",
    siteInfo: "Site Information",
    addNewSite: "Add New Site",
    siteName: "Site Name",
    locationCode: "Location Code",
    safetyManager: "Safety Manager",
    emergencyContact: "Emergency Contact",
    zoneConfigs: "Zone Configurations",
    edit: "Edit",
    editRoi: "Edit ROI",
    faceBlurring: "Face Blurring (Privacy)",
    privacyDesc: "Automatically blur faces in all video feeds for compliance.",
    pushNotifications: "Push Notifications",
    pushDesc: "Send real-time alerts to mobile devices and email.",
  },
  ar: {
    // Nav
    overview: "الرئيسية",
    liveFeeds: "المراقبة الحية",
    alerts: "التنبيهات",
    incidents: "سجل الحوادث",
    ergonomics: "تحليل وضعيات العمل",
    reports: "التحليلات",
    users: "إدارة المستخدمين",
    cameras: "إدارة الكاميرات",
    health: "صحة النظام",
    monitoring: "مراقبة السلامة",
    analytics: "البيانات والتقارير",
    system: "إدارة النظام",
    configuration: "الإعدادات",
    
    // Header
    systemActive: "سيرفر الحافة متصل",
    systemOffline: "سيرفر الحافة غير متصل",
    systemOptimal: "النظام مثالي",
    searchPlaceholder: "بحث في السجلات...",
    logout: "خروج",

    // KPIs
    mtta: "متوسط زمن الاستجابة (MTTA)",
    mttr: "متوسط زمن الإغلاق (MTTR)",
    safetyScore: "نسبة الامتثال",
    activeAlerts: "تنبيهات نشطة",
    lastUpdated: "آخر تحديث",

    // Severity
    high: "عالي",
    medium: "متوسط",
    low: "منخفض",

    // Ergonomics
    ergonomicExposure: "التعرض لمخاطر الوضعيات",
    rulaScore: "متوسط مؤشر RULA",
    riskyDuration: "مدة الوضعيات الخطرة",
    badPostures: "وضعيات خاطئة مكتشفة",
    ergoTrends: "اتجاهات الهندسة البشرية",
    riskByZone: "توزيع المخاطر حسب المنطقة",

    // Health
    edgeNodes: "عقد حوسبة الحافة",
    nodeStatus: "حالة العقدة",
    latency: "زمن الاستجابة",
    uptime: "وقت التشغيل",
    storage: "صحة التخزين",
    cpuUsage: "استهلاك المعالج",
    
    // Dashboard & Others
    safetyOverview: "حالة سلامة المصنع",
    realTimeMonitoring: "المراقبة الذكية نشطة حالياً.",
    camerasOnline: "المستشعرات المتصلة",
    incidentTrends: "اتجاهات السلامة (أسبوعي)",
    criticalZones: "المناطق عالية الخطورة",
    viewAllZones: "عرض الخريطة",
    liveIncidentFeed: "النشاط الأخير",
    viewAllEvents: "السجل الكامل",
    highRisk: "خطر",
    processing: "نشط",
    allZones: "كل المناطق",
    
    // Statuses
    new: "جديد",
    notified: "تم الإخطار",
    acknowledged: "تم الإقرار",
    resolved: "تم الحل",
    dismissed: "مرفوض",
    archived: "مؤرشف",
    active: "نشط",
    inactive: "غير نشط",
    logged: "مسجل",
    investigation: "قيد التحقيق",
    online: "متصل",
    offline: "غير متصل",
    
    // General
    zoneA: "الإنتاج أ",
    zoneB: "المستودع ب",
    zoneC: "منصة التحميل",
    zoneD: "خط التجميع",
    admin: "مسؤول النظام",
    safetyengineer: "مهندس سلامة",
    dataanalyst: "محلل بيانات",
    reportIncident: "إبلاغ عن حادث جديد",
    exportCSV: "تصدير البيانات",
    addUser: "إضافة مستخدم",
    addCamera: "إضافة بث",
    cameraName: "اسم البث",
    rtspUrl: "رابط المصدر",
    location: "المنطقة",
    saveChanges: "حفظ الإعدادات",

    // Filters
    allSeverities: "كل المستويات",
    allTypes: "كل الأنواع",
    allStatuses: "كل الحالات",
    filter: "تصفية",

    // Actions & Messages
    noResults: "لا توجد نتائج.",
    notifications: "الإشعارات",
    noNotifications: "لا توجد إشعارات جديدة",
    markAllRead: "تحديد الكل كمقروء",
    confirmDelete: "هل أنت متأكد من الحذف؟",
    deleteSuccess: "تم الحذف بنجاح!",
    addedSuccessfully: "تمت الإضافة بنجاح!",
    close: "إغلاق",
    delete: "حذف",
    cancel: "إلغاء",
    submit: "إرسال",
    acknowledge: "إقرار",
    resolve: "حل",
    escalate: "تصعيد كحادث",

    // Table headers
    id: "الرمز",
    alertType: "النوع",
    severity: "الخطورة",
    timestamp: "الوقت",
    status: "الحالة",
    action: "الإجراء",
    alertDetails: "تفاصيل التنبيه",
    date: "التاريخ",
    category: "التصنيف",
    description: "الوصف",

    // Configuration
    systemConfiguration: "إعدادات النظام",
    sitesZones: "المواقع والمناطق",
    policies: "السياسات",
    integrations: "التكاملات",
    siteInfo: "معلومات الموقع",
    addNewSite: "إضافة موقع جديد",
    siteName: "اسم الموقع",
    locationCode: "رمز الموقع",
    safetyManager: "مسؤول السلامة",
    emergencyContact: "رقم الطوارئ",
    zoneConfigs: "إعدادات المناطق",
    edit: "تعديل",
    editRoi: "تعديل ROI",
    faceBlurring: "تأمين الوجوه (الخصوصية)",
    privacyDesc: "تشويش الوجوه تلقائياً في جميع البث المرئي للامتثال.",
    pushNotifications: "الإشعارات الفورية",
    pushDesc: "إرسال تنبيهات فورية للأجهزة المحمولة والبريد الإلكتروني.",
  }
};

const LanguageContext = createContext<any>(null);

export const LanguageProvider = ({ children }: { children?: React.ReactNode }) => {
  const [language, setLanguage] = useState<Language>('ar');
  const dir = language === 'ar' ? 'rtl' : 'ltr';

  const t = (key: keyof typeof translations['en']) => {
    // @ts-ignore
    return translations[language][key] || key;
  };

  return (
    <LanguageContext.Provider value={{ language, setLanguage, dir, t }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = () => useContext(LanguageContext);
