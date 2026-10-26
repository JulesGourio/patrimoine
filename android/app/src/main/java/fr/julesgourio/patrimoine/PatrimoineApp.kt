package fr.julesgourio.patrimoine

import android.app.Application
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Notifier
import fr.julesgourio.patrimoine.work.Scheduler

class PatrimoineApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Engine.attach(this)
        Notifier.createChannels(this)
        Scheduler.ensure(this)
    }
}
