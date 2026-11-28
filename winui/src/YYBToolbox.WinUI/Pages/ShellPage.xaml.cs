using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using YYBToolbox.WinUI.Services;

namespace YYBToolbox.WinUI.Pages;

public sealed partial class ShellPage : UserControl
{
    public ShellPage()
    {
        InitializeComponent();
    }

    private void OnCommandKeyDown(object sender, KeyRoutedEventArgs e)
    {
        if (e.Key == Windows.System.VirtualKey.Enter)
        {
            e.Handled = true;
            _ = RunCommandAsync();
        }
    }

    private async void OnRunClicked(object sender, RoutedEventArgs e) => await RunCommandAsync();

    private async Task RunCommandAsync()
    {
        var cmd = CommandBox.Text?.Trim() ?? "";
        if (string.IsNullOrEmpty(cmd)) return;

        AppState.Current.SetStatus($"执行：{cmd}");
        Append($"$ {cmd}\n");
        try
        {
            var result = await Task.Run(() => AppState.Current.Adb.Shell(cmd, timeout: 60));
            Append(result + "\n\n");
            AppState.Current.SetStatus("命令执行完成");
        }
        catch (Exception ex)
        {
            Append($"错误：{ex.Message}\n\n");
            AppState.Current.SetStatus($"命令执行失败：{ex.Message}");
        }
    }

    private void Append(string text)
    {
        OutputBox.Text += text;
        OutputBox.SelectionStart = OutputBox.Text.Length;
    }
}
