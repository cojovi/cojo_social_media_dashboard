export const SIDEBAR_PREFERENCE_KEY = 'reelvault:sidebar-collapsed:v1';
export const FOLDER_SIDEBAR_PREFERENCE_KEY = 'reelvault:folder-sidebar-collapsed:v1';

function readCollapsed(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === 'true';
  } catch {
    // Navigation still works when browser storage is blocked or unavailable.
    return false;
  }
}

function saveCollapsed(key: string, collapsed: boolean): void {
  try {
    window.localStorage.setItem(key, String(collapsed));
  } catch {
    // Remembering the preference is optional; never block a layout change.
  }
}

export const readSidebarCollapsed = (): boolean => readCollapsed(SIDEBAR_PREFERENCE_KEY);
export const saveSidebarCollapsed = (collapsed: boolean): void => saveCollapsed(SIDEBAR_PREFERENCE_KEY, collapsed);
export const readFolderSidebarCollapsed = (): boolean => readCollapsed(FOLDER_SIDEBAR_PREFERENCE_KEY);
export const saveFolderSidebarCollapsed = (collapsed: boolean): void => saveCollapsed(FOLDER_SIDEBAR_PREFERENCE_KEY, collapsed);
