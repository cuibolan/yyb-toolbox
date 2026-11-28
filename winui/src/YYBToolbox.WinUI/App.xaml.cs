using System.IO;
using Microsoft.UI.Xaml;

namespace YYBToolbox.WinUI;

public partial class App : Application
{
    private Window? _window;
    private static readonly string LogFile = Path.Combine(AppContext.BaseDirectory, "startup.log");

    public App()
    {
        try
        {
            InitializeComponent();
            AppDomain.CurrentDomain.UnhandledException += (s, e) =>
                WriteLog("UnhandledException: " + e.ExceptionObject);
            UnhandledException += (s, e) =>
            {
                var ex = e.Exception;
                WriteLog($"DispatcherUnhandledException: {ex}\n{ex?.StackTrace}\nInner: {ex?.InnerException}");
                e.Handled = true;
            };        }
        catch (Exception ex)
        {
            WriteLog("App ctor: " + ex);
            throw;
        }
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        try
        {
            _window = new MainWindow();
            _window.Activate();
        }
        catch (Exception ex)
        {
            WriteLog("OnLaunched: " + ex);
            throw;
        }
    }

    private static void WriteLog(object? content)
    {
        try { File.AppendAllText(LogFile, $"[{DateTime.Now:HH:mm:ss}] {content}\n"); } catch { }
    }
}
