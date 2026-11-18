package nl.squadtracker.app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

public class MainActivity extends Activity {
    private WebView web;
    private SwipeRefreshLayout refresh;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(R.layout.activity_main);
        web = findViewById(R.id.web);
        refresh = findViewById(R.id.refresh);
        web.setBackgroundColor(Color.parseColor("#0B1118"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setUserAgentString(s.getUserAgentString() + " SquadTrackerApp");
        final String home = BuildConfig.SITE_URL;
        final String host = Uri.parse(home).getHost();
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                Uri u = req.getUrl();
                if (host != null && host.equals(u.getHost())) return false;
                startActivity(new Intent(Intent.ACTION_VIEW, u)); // externe links in de browser
                return true;
            }
            @Override
            public void onPageFinished(WebView v, String url) { refresh.setRefreshing(false); }
        });
        // alleen verversen als je bovenaan de pagina bent
        refresh.setOnChildScrollUpCallback((parent, child) -> web.getScrollY() > 0);
        refresh.setOnRefreshListener(() -> web.reload());
        refresh.setColorSchemeColors(Color.parseColor("#FF4655"));
        refresh.setProgressBackgroundColorSchemeColor(Color.parseColor("#152130"));
        if (state != null) web.restoreState(state); else web.loadUrl(home);
    }

    @Override
    protected void onSaveInstanceState(Bundle out) { super.onSaveInstanceState(out); web.saveState(out); }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
}
