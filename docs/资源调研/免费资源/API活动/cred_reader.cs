using System;
using System.Runtime.InteropServices;
using System.Text;

class Program {
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CredEnumerate(string filter, uint flags, out int count, out IntPtr credsPtr);
    [DllImport("advapi32.dll")]
    public static extern void CredFree(IntPtr credPtr);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct CREDENTIALW {
        public uint Flags;
        public uint Type;
        public IntPtr TargetName;
        public IntPtr Comment;
        public ulong LastWritten;
        public uint CredentialBlobSize;
        public IntPtr CredentialBlob;
        public uint PersistenceType;
        public IntPtr Attributes;
        public IntPtr TargetAlias;
        public IntPtr UserName;
    }

    static void Main() {
        IntPtr ptr;
        int count;
        if (!CredEnumerate(null, 0, out count, out ptr)) {
            Console.Error.WriteLine("CredEnumerate failed: " + Marshal.GetLastWin32Error());
            Environment.Exit(1);
        }

        var entries = new IntPtr[count];
        Marshal.Copy(ptr, entries, 0, count);
        CredFree(ptr);

        string targetFilter = "cli_aad5db8438385d04";
        string foundSecret = null;

        for (int i = 0; i < count; i++) {
            var cred = (CREDENTIALW)Marshal.PtrToStructure(entries[i], typeof(CREDENTIALW));
            string target = Marshal.PtrToStringUni(cred.TargetName) ?? "";
            if (target.Contains(targetFilter)) {
                Console.Error.WriteLine("Found: Type=" + cred.Type + " Target=" + target);
                var blob = new byte[cred.CredentialBlobSize];
                Marshal.Copy(cred.CredentialBlob, blob, 0, (int)cred.CredentialBlobSize);
                foundSecret = Encoding.Unicode.GetString(blob).TrimEnd('\0');
                break;
            }
        }

        if (foundSecret != null) {
            Console.Write(foundSecret);
        } else {
            Console.Error.WriteLine("Credential not found. Total: " + count);
            for (int i = 0; i < Math.Min(5, count); i++) {
                var cred = (CREDENTIALW)Marshal.PtrToStructure(entries[i], typeof(CREDENTIALW));
                Console.Error.WriteLine("  [" + i + "] Type=" + cred.Type + " Target=" + Marshal.PtrToStringUni(cred.TargetName));
            }
            Environment.Exit(1);
        }
    }
}
