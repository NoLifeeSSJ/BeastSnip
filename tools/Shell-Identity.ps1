# Windows taskbar identity, shared with beastsnip/windows.py. Loading is inert.
function Initialize-BeastSnipShellIdentity {
    if ('BeastSnipShellIdentity' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class BeastSnipShellIdentity {
    public const string AppId = "NoLifeeSSJ.BeastSnip.Desktop";
    [StructLayout(LayoutKind.Sequential)]
    public struct PropertyKey {
        public Guid format;
        public uint id;
        public PropertyKey(uint value) { format = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"); id = value; }
    }
    [StructLayout(LayoutKind.Explicit, Size = 24)]
    public struct PropertyValue {
        [FieldOffset(0)] public ushort type;
        [FieldOffset(8)] public IntPtr text;
    }
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface PropertyStore {
        [PreserveSig] int GetCount(out uint count);
        [PreserveSig] int GetAt(uint index, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out PropertyValue value);
        [PreserveSig] int SetValue(ref PropertyKey key, ref PropertyValue value);
        [PreserveSig] int Commit();
    }
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    static extern int SHGetPropertyStoreFromParsingName(string path, IntPtr context, uint flags, ref Guid iid, out PropertyStore store);
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    static extern void SHChangeNotify(uint change, uint flags, string item, IntPtr other);
    [DllImport("ole32.dll")]
    static extern int PropVariantClear(ref PropertyValue value);

    static PropertyStore Open(string path, uint flags) {
        Guid iid = typeof(PropertyStore).GUID;
        PropertyStore store;
        Marshal.ThrowExceptionForHR(SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, flags, ref iid, out store));
        return store;
    }
    static void Set(PropertyStore store, uint id, string text) {
        var key = new PropertyKey(id);
        var value = new PropertyValue { type = 31, text = Marshal.StringToCoTaskMemUni(text) };
        try { Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value)); }
        finally { Marshal.FreeCoTaskMem(value.text); }
    }
    public static void Configure(string path, string icon, string command) {
        var store = Open(path, 2); // GPS_READWRITE
        try {
            Set(store, 5, AppId);
            Set(store, 3, icon + ",0");
            Set(store, 4, "BeastSnip");
            Set(store, 2, command);
            Marshal.ThrowExceptionForHR(store.Commit());
        } finally { Marshal.ReleaseComObject(store); }
        if (ReadAppId(path) != AppId) throw new InvalidOperationException("The shortcut application identity did not persist.");
        SHChangeNotify(0x00002000, 0x0005, path, IntPtr.Zero); // UPDATEITEM, PATHW
    }
    public static string ReadAppId(string path) {
        var store = Open(path, 0);
        try {
            var key = new PropertyKey(5);
            PropertyValue value;
            Marshal.ThrowExceptionForHR(store.GetValue(ref key, out value));
            try { return value.type == 31 ? Marshal.PtrToStringUni(value.text) : null; }
            finally { PropVariantClear(ref value); }
        } finally { Marshal.ReleaseComObject(store); }
    }
}
'@
}

function Set-BeastSnipShortcutIdentity {
    param([string]$ShortcutPath, [string]$IconPath, [string]$RelaunchCommand)
    Initialize-BeastSnipShellIdentity
    [BeastSnipShellIdentity]::Configure($ShortcutPath, $IconPath, $RelaunchCommand)
}
